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
        fishbowl_system: "odoo.model.external_system",
        sync_started_at: datetime,
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
        receipt_line_batch_size = 500
        receipt_ids = {row.receiptId for row in receipt_item_rows if row.receiptId is not None}
        receipt_existing_map: dict[str, int] = {}
        _receipt_stale_map: dict[str, "odoo.model.external_id"] = {}
        receipt_blocked: set[str] = set()
        receipt_latest_dates: dict[int, datetime] = {}
        receipt_line_totals: dict[int, int] = {}
        receipt_line_success: dict[int, int] = {}
        receipt_line_blocked: set[int] = set()
        for row in receipt_item_rows:
            if row.receiptId is None or row.dateReceived is None:
                continue
            receipt_line_totals[row.receiptId] = receipt_line_totals.get(row.receiptId, 0) + 1
            latest = receipt_latest_dates.get(row.receiptId)
            if not latest or row.dateReceived > latest:
                receipt_latest_dates[row.receiptId] = row.dateReceived
        receipts_to_process: set[int] = set()
        if receipt_ids:
            receipt_external_ids = [str(value) for value in receipt_ids]
            receipt_existing_map, _receipt_stale_map, receipt_blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_RECEIPT,
                receipt_external_ids,
                "stock.picking",
            )
            for receipt_id in receipt_ids:
                updated_at = receipt_latest_dates.get(receipt_id)
                if not updated_at:
                    continue
                if self._should_process_external_row(
                    fishbowl_system,
                    str(receipt_id),
                    RESOURCE_RECEIPT,
                    updated_at,
                ):
                    receipts_to_process.add(receipt_id)

        for start_index in range(0, len(receipt_item_rows), receipt_line_batch_size):
            batch_rows = receipt_item_rows[start_index : start_index + receipt_line_batch_size]
            (
                existing_map,
                stale_map,
                blocked,
                create_values,
                create_external_ids,
                move_line_payloads,
                batch_move_ids,
                processed_external_ids,
            ) = self._prepare_stock_move_batch(
                fishbowl_system.id,
                RESOURCE_RECEIPT_LINE,
                batch_rows,
            )
            receipt_line_map: dict[str, int] = {}

            for row in batch_rows:
                receipt_id = row.receiptId
                if receipt_id is None:
                    continue
                fishbowl_receipt_id = receipt_id
                receipt_external_id_value = str(fishbowl_receipt_id)
                if receipt_external_id_value in receipt_blocked:
                    receipt_line_blocked.add(fishbowl_receipt_id)
                    continue
                updated_at = receipt_latest_dates.get(fishbowl_receipt_id)
                if updated_at and fishbowl_receipt_id not in receipts_to_process:
                    continue
                picking_id = done_picking_ids.get(fishbowl_receipt_id)
                if not picking_id:
                    purchase_order_id = order_maps["purchase_order"].get(row.poId or 0)
                    partner_id = False
                    if purchase_order_id:
                        partner_id = self.env["purchase.order"].sudo().browse(purchase_order_id).partner_id.id
                    values = {
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
                        update_values = dict(values)
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
                    receipt_line_blocked.add(fishbowl_receipt_id)
                    continue
                product_id = self._resolve_product_from_receipt_row(row, order_maps, product_maps)
                # noinspection DuplicatedCode
                # Receipt/shipment line handling stays explicit to keep line-field differences readable.
                if not product_id:
                    receipt_line_blocked.add(fishbowl_receipt_id)
                    continue
                product = self.env["product.product"].sudo().browse(product_id)
                if not self._is_stockable_product(product):
                    receipt_line_success[fishbowl_receipt_id] = receipt_line_success.get(fishbowl_receipt_id, 0) + 1
                    continue
                unit_id = unit_map.get(row.uomId or 0)
                quantity_received = row.qty or 0
                picking = picking_model.browse(picking_id)
                move_values = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_received),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "purchase_line_id": order_maps["purchase_line"].get(row.poItemId or 0) or False,
                }
                # noinspection DuplicatedCode
                # Receipt/shipment move handling stays explicit to keep order-line differences readable.
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
                        processed_external_ids.append(external_id_value)
                        receipt_line_success[fishbowl_receipt_id] = receipt_line_success.get(fishbowl_receipt_id, 0) + 1
                        continue
                    existing_move.write(move_values)
                    batch_move_ids[external_id_value] = existing_move_id
                    processed_external_ids.append(external_id_value)
                    receipt_line_success[fishbowl_receipt_id] = receipt_line_success.get(fishbowl_receipt_id, 0) + 1
                    continue
                create_values.append(move_values)
                create_external_ids.append(external_id_value)
                receipt_line_map[external_id_value] = fishbowl_receipt_id

            created_move_ids = self._create_stock_moves_with_external_ids(
                move_model,
                create_values=create_values,
                create_external_ids=create_external_ids,
                stale_map=stale_map,
                system_id=fishbowl_system.id,
                resource=RESOURCE_RECEIPT_LINE,
            )
            for external_id_value, move_id in created_move_ids.items():
                batch_move_ids[external_id_value] = move_id
                processed_external_ids.append(external_id_value)
                receipt_id = receipt_line_map.get(external_id_value)
                if receipt_id:
                    receipt_line_success[receipt_id] = receipt_line_success.get(receipt_id, 0) + 1
            if processed_external_ids:
                self._mark_external_ids_synced(
                    fishbowl_system.id,
                    RESOURCE_RECEIPT_LINE,
                    processed_external_ids,
                    sync_started_at,
                )

            self._ensure_stock_move_lines(
                move_model,
                move_line_model,
                batch_move_ids,
                move_line_payloads,
            )

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

        if receipts_to_process:
            synced_receipts = 0
            for receipt_id in receipts_to_process:
                if receipt_id in receipt_line_blocked:
                    continue
                total_lines = receipt_line_totals.get(receipt_id, 0)
                if total_lines <= 0:
                    continue
                if receipt_line_success.get(receipt_id, 0) != total_lines:
                    continue
                updated_at = receipt_latest_dates.get(receipt_id)
                if not updated_at:
                    continue
                self._mark_external_id_synced(
                    fishbowl_system,
                    str(receipt_id),
                    RESOURCE_RECEIPT,
                    updated_at,
                )
                synced_receipts += 1
            if synced_receipts:
                _logger.info("Fishbowl import: synced %s receipts", synced_receipts)
