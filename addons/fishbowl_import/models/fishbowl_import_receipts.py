import logging
import time
from datetime import datetime
from odoo import models

from ..services.fishbowl_client import FishbowlClient
from . import fishbowl_rows
from .fishbowl_import_constants import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_RECEIPT, RESOURCE_RECEIPT_LINE

_logger = logging.getLogger(__name__)


# External Fishbowl schema; SQL resolver has no catalog.
# noinspection SqlResolve
class FishbowlImporterReceipts(models.Model):
    _inherit = "fishbowl.importer"

    def _import_receipts(
        self,
        client: FishbowlClient,
        order_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> None:
        receipt_status_map = self._load_status_map(client, "receiptstatus")
        done_statuses = {"received", "fulfilled"}
        done_status_ids = [
            status_id for status_id, status_name in receipt_status_map.items() if status_name.lower() in done_statuses
        ]
        if not done_status_ids:
            _logger.warning("No receipt statuses mapped for completion; skipping receipts.")
            return

        picking_model = self.env["stock.picking"].sudo().with_context(IMPORT_CONTEXT)
        move_model = self.env["stock.move"].sudo().with_context(IMPORT_CONTEXT)
        move_line_model = self.env["stock.move.line"].sudo().with_context(IMPORT_CONTEXT)

        picking_type = self._get_picking_type("incoming")
        if not picking_type:
            _logger.warning("No incoming picking type found; skipping receipts.")
            return
        source_location = picking_type.default_location_src_id or self._get_location("supplier")
        destination_location = picking_type.default_location_dest_id or self._get_location("internal")

        status_placeholders = ", ".join(["%s"] * len(done_status_ids))
        receipt_conditions = ["ri.dateReceived IS NOT NULL", f"r.statusId IN ({status_placeholders})"]
        receipt_params: list[int | datetime] = list(done_status_ids)
        if start_datetime:
            receipt_conditions.append("ri.dateReceived >= %s")
            receipt_params.append(start_datetime)
        receipt_where = " AND ".join(receipt_conditions)
        receipt_query = (
            "SELECT ri.id, ri.receiptId, ri.poItemId, ri.qty, ri.uomId, ri.dateReceived, ri.partId, r.poId "
            "FROM receiptitem ri JOIN receipt r ON r.id = ri.receiptId "
            f"WHERE {receipt_where} ORDER BY ri.id"
        )
        receipt_item_rows: list[fishbowl_rows.ReceiptItemRow] = fishbowl_rows.RECEIPT_ITEM_ROWS_ADAPTER.validate_python(
            client.fetch_all(receipt_query, receipt_params)
        )

        unit_map = self._load_unit_map()
        done_picking_ids: dict[int, int] = {}
        receipt_line_processed = 0
        receipt_line_log_every = 5000
        receipt_line_log_threshold = receipt_line_log_every
        receipt_line_started_at = time.monotonic()
        receipt_line_batch_size = 2000
        fishbowl_system = self._get_fishbowl_system()
        receipt_ids = {row.receiptId for row in receipt_item_rows if row.receiptId is not None}
        receipt_existing_map: dict[str, int] = {}
        _receipt_stale_map: dict[str, "odoo.model.external_id"] = {}
        receipt_blocked: set[str] = set()
        if receipt_ids:
            receipt_external_ids = [str(value) for value in receipt_ids]
            receipt_existing_map, _receipt_stale_map, receipt_blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_RECEIPT,
                receipt_external_ids,
                "stock.picking",
            )

        for start_index in range(0, len(receipt_item_rows), receipt_line_batch_size):
            # noinspection DuplicatedCode
            batch_rows = receipt_item_rows[start_index : start_index + receipt_line_batch_size]
            external_ids = [str(row.id) for row in batch_rows]
            existing_map, stale_map, blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_RECEIPT_LINE,
                external_ids,
                "stock.move",
            )
            create_values: list["odoo.values.stock_move"] = []
            create_external_ids: list[str] = []
            move_line_payloads: dict[str, "odoo.values.stock_move_line"] = {}
            batch_move_ids: dict[str, int] = {}

            for row in batch_rows:
                receipt_id = row.receiptId
                if receipt_id is None:
                    continue
                fishbowl_receipt_id = receipt_id
                receipt_external_id_value = str(fishbowl_receipt_id)
                if receipt_external_id_value in receipt_blocked:
                    continue
                picking_id = done_picking_ids.get(fishbowl_receipt_id)
                if not picking_id:
                    purchase_order_id = order_maps["purchase_order"].get(row.poId or 0)
                    partner_id = False
                    if purchase_order_id:
                        partner_id = self.env["purchase.order"].sudo().browse(purchase_order_id).partner_id.id
                    values: "odoo.values.stock_picking" = {
                        "picking_type_id": picking_type.id,
                        "location_id": source_location.id,
                        "location_dest_id": destination_location.id,
                        "partner_id": partner_id or False,
                        "origin": row.receiptId,
                        "purchase_id": purchase_order_id or False,
                        "scheduled_date": row.dateReceived,
                        "date_done": row.dateReceived,
                    }
                    existing_picking_id = receipt_existing_map.get(receipt_external_id_value)
                    if existing_picking_id:
                        picking = picking_model.browse(existing_picking_id)
                        if picking.picking_type_id.id != picking_type.id:
                            _logger.warning(
                                "Receipt %s has picking type %s (expected %s); skipping operation type update.",
                                picking.name,
                                picking.picking_type_id.display_name,
                                picking_type.display_name,
                            )
                        update_values: "odoo.values.stock_picking" = dict(values)
                        update_values.pop("picking_type_id", None)
                        update_values.pop("location_id", None)
                        update_values.pop("location_dest_id", None)
                        self._write_if_changed(picking, update_values)
                        picking_id = picking.id
                        done_picking_ids[fishbowl_receipt_id] = picking_id
                    else:
                        picking = picking_model.get_or_create_by_external_id(
                            EXTERNAL_SYSTEM_CODE,
                            receipt_external_id_value,
                            values,
                            RESOURCE_RECEIPT,
                        )
                        picking_id = picking.id
                        done_picking_ids[fishbowl_receipt_id] = picking_id

                fishbowl_line_id = row.id
                external_id_value = str(fishbowl_line_id)
                if external_id_value in blocked:
                    continue
                product_id = self._resolve_product_from_receipt_row(row, order_maps, product_maps)
                if not product_id:
                    continue
                product = self.env["product.product"].sudo().browse(product_id)
                if not self._is_stockable_product(product):
                    continue
                unit_id = unit_map.get(row.uomId or 0)
                quantity_received = row.qty or 0
                picking = picking_model.browse(picking_id)
                move_values: "odoo.values.stock_move" = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_received),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "purchase_line_id": order_maps["purchase_line"].get(row.poItemId or 0) or False,
                }
                # noinspection DuplicatedCode
                move_line_payloads[external_id_value] = {
                    "product_id": product_id,
                    "product_uom_id": unit_id or product.uom_id.id,
                    "qty_done": float(quantity_received),
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                }
                existing_move_id = existing_map.get(external_id_value)
                if existing_move_id:
                    existing_move = move_model.browse(existing_move_id)
                    if existing_move.state == "done":
                        batch_move_ids[external_id_value] = existing_move_id
                        continue
                    existing_move.write(move_values)
                    batch_move_ids[external_id_value] = existing_move_id
                    continue
                create_values.append(move_values)
                create_external_ids.append(external_id_value)

            # noinspection DuplicatedCode
            if create_values:
                created_moves = move_model.create(create_values)
                external_id_payloads: list["odoo.values.external_id"] = []
                for external_id_value, move in zip(create_external_ids, created_moves, strict=True):
                    batch_move_ids[external_id_value] = move.id
                    stale_record = stale_map.pop(external_id_value, None)
                    if stale_record:
                        stale_record.write({"res_model": "stock.move", "res_id": move.id, "active": True})
                        continue
                    external_id_payloads.append(
                        {
                            "res_model": "stock.move",
                            "res_id": move.id,
                            "system_id": fishbowl_system.id,
                            "resource": RESOURCE_RECEIPT_LINE,
                            "external_id": external_id_value,
                            "active": True,
                        }
                    )
                if external_id_payloads:
                    self.env["external.id"].sudo().create(external_id_payloads)

            for external_id_value, move_id in batch_move_ids.items():
                move = move_model.browse(move_id)
                if move.move_line_ids:
                    continue
                move_line_values = move_line_payloads.get(external_id_value)
                if not move_line_values:
                    continue
                move_line_values["move_id"] = move.id
                move_line_model.create(move_line_values)

            receipt_line_processed += len(batch_rows)
            if receipt_line_processed >= receipt_line_log_threshold:
                elapsed = time.monotonic() - receipt_line_started_at
                _logger.info(
                    "Fishbowl import: receipt lines processed %s in %.2fs",
                    receipt_line_processed,
                    elapsed,
                )
                receipt_line_log_threshold += receipt_line_log_every
            self._commit_and_clear()

        if receipt_item_rows:
            receipt_elapsed = time.monotonic() - receipt_line_started_at
            _logger.info("Fishbowl import: receipt lines complete in %.2fs", receipt_elapsed)

        if done_picking_ids:
            finalize_started_at = time.monotonic()
            total_pickings = len(done_picking_ids)
            _logger.info("Fishbowl import: finalizing %s receipts", total_pickings)
            finalized_count = 0
            finalize_log_every = 500
            for picking_id in done_picking_ids.values():
                self._finalize_picking(picking_model.browse(picking_id))
                finalized_count += 1
                if finalized_count % finalize_log_every == 0:
                    elapsed = time.monotonic() - finalize_started_at
                    _logger.info(
                        "Fishbowl import: finalized %s/%s receipts in %.2fs",
                        finalized_count,
                        total_pickings,
                        elapsed,
                    )
                    self._commit_and_clear()
            self._commit_and_clear()
            finalize_elapsed = time.monotonic() - finalize_started_at
            _logger.info("Fishbowl import: finalized %s receipts in %.2fs", total_pickings, finalize_elapsed)
