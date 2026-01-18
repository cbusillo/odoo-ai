import logging
import time
from datetime import datetime
from odoo import models

from ..services.fishbowl_client import FishbowlClient
from . import fishbowl_rows
from .fishbowl_import_constants import (
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    RESOURCE_SALES_ORDER_LINE,
    RESOURCE_SHIPMENT,
    RESOURCE_SHIPMENT_LINE,
)

_logger = logging.getLogger(__name__)


class FishbowlImporterShipments(models.Model):
    _inherit = "fishbowl.importer"

    def _import_shipments(
        self,
        client: FishbowlClient,
        order_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> None:
        shipment_rows = self._fetch_orders(
            client,
            "ship",
            "dateShipped",
            start_datetime,
            extra_where="dateShipped IS NOT NULL",
            select_columns="id, num, statusId, soId, dateShipped, dateCreated",
        )
        shipment_rows = fishbowl_rows.ORDER_ROWS_ADAPTER.validate_python(shipment_rows)
        shipment_status_map = self._load_status_map(client, "shipstatus")
        fishbowl_system = self._get_fishbowl_system()
        picking_model = self.env["stock.picking"].sudo().with_context(IMPORT_CONTEXT)
        move_model = self.env["stock.move"].sudo().with_context(IMPORT_CONTEXT)
        move_line_model = self.env["stock.move.line"].sudo().with_context(IMPORT_CONTEXT)

        picking_type = self._get_picking_type("outgoing")
        if not picking_type:
            _logger.warning("No outgoing picking type found; skipping shipments.")
            return
        source_location = picking_type.default_location_src_id or self._get_location("internal")
        destination_location = picking_type.default_location_dest_id or self._get_location("customer")

        shipment_map: dict[int, int] = {}
        done_picking_ids: list[int] = []

        shipped_rows: list[fishbowl_rows.OrderRow] = []
        for row in shipment_rows:
            status_name = shipment_status_map.get(row.statusId or 0, "")
            if status_name.lower() != "shipped":
                continue
            shipped_rows.append(row)

        shipment_external_ids = [str(row.id) for row in shipped_rows]
        shipment_existing_map, shipment_stale_map, shipment_blocked = self._prefetch_external_id_records(
            fishbowl_system.id,
            RESOURCE_SHIPMENT,
            shipment_external_ids,
            "stock.picking",
        )

        for row in shipped_rows:
            fishbowl_id = row.id
            external_id_value = str(fishbowl_id)
            if external_id_value in shipment_blocked:
                continue
            sale_order_id = order_maps["sales_order"].get(row.soId or 0)
            partner_id = False
            if sale_order_id:
                partner_id = self.env["sale.order"].sudo().browse(sale_order_id).partner_id.id
            values: "odoo.values.stock_picking" = {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "partner_id": partner_id or False,
                "origin": row.num or False,
                "sale_id": sale_order_id or False,
                "scheduled_date": row.dateShipped or row.dateCreated,
                "date_done": row.dateShipped,
            }
            existing_picking_id = shipment_existing_map.get(external_id_value)
            if existing_picking_id:
                picking = picking_model.browse(existing_picking_id)
                shipment_map[fishbowl_id] = picking.id
                done_picking_ids.append(picking.id)
                if picking.picking_type_id.id != picking_type.id:
                    _logger.warning(
                        "Shipment %s has picking type %s (expected %s); skipping operation type update.",
                        picking.name,
                        picking.picking_type_id.display_name,
                        picking_type.display_name,
                    )
                update_values: "odoo.values.stock_picking" = dict(values)
                update_values.pop("picking_type_id", None)
                update_values.pop("location_id", None)
                update_values.pop("location_dest_id", None)
                self._write_if_changed(picking, update_values)
                continue
            picking = picking_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                values,
                RESOURCE_SHIPMENT,
            )
            shipment_map[fishbowl_id] = picking.id
            done_picking_ids.append(picking.id)

        if not shipment_map:
            return
        shipment_item_rows: list[fishbowl_rows.ShipmentLineRow] = self._fetch_rows_by_ids(
            client,
            "shipitem",
            "shipId",
            list(shipment_map.keys()),
            select_columns="id, shipId, soItemId, qtyShipped, uomId",
            row_parser=fishbowl_rows.SHIPMENT_LINE_ROWS_ADAPTER.validate_python,
        )
        missing_sales_line_ids = {
            row.soItemId for row in shipment_item_rows if row.soItemId is not None and row.soItemId not in order_maps["sales_line"]
        }
        sales_line_external_map: dict[int, int] = {}
        if missing_sales_line_ids:
            external_id_records = (
                self.env["external.id"]
                .sudo()
                .search(
                    [
                        ("system_id", "=", fishbowl_system.id),
                        ("resource", "=", RESOURCE_SALES_ORDER_LINE),
                        ("res_model", "=", "sale.order.line"),
                        ("active", "=", True),
                        ("external_id", "in", [str(value) for value in missing_sales_line_ids]),
                    ]
                )
            )
            for record in external_id_records:
                try:
                    sales_line_external_map[int(record.external_id)] = record.res_id
                except (TypeError, ValueError):
                    _logger.warning("Invalid Fishbowl sales line external id '%s'", record.external_id)
        unit_map = self._load_unit_map()
        shipment_line_processed = 0
        shipment_line_log_every = 10000
        shipment_line_log_threshold = shipment_line_log_every
        shipment_line_started_at = time.monotonic()
        shipment_line_batch_size = 2000
        # noinspection DuplicatedCode
        for start_index in range(0, len(shipment_item_rows), shipment_line_batch_size):
            # noinspection DuplicatedCode
            batch_rows = shipment_item_rows[start_index : start_index + shipment_line_batch_size]
            external_ids = [str(row.id) for row in batch_rows]
            existing_map, stale_map, blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_SHIPMENT_LINE,
                external_ids,
                "stock.move",
            )
            create_values: list["odoo.values.stock_move"] = []
            create_external_ids: list[str] = []
            move_line_payloads: dict[str, "odoo.values.stock_move_line"] = {}
            batch_move_ids: dict[str, int] = {}

            # noinspection DuplicatedCode
            for row in batch_rows:
                ship_id = row.shipId
                if ship_id is None:
                    continue
                picking_id = shipment_map.get(ship_id)
                if not picking_id:
                    continue
                fishbowl_id = row.id
                external_id_value = str(fishbowl_id)
                if external_id_value in blocked:
                    continue
                picking = picking_model.browse(picking_id)
                sales_line = self._resolve_sales_line_for_shipment_row(
                    row,
                    order_maps,
                    sales_line_external_map,
                )
                sale_line_id = sales_line.id if sales_line else False
                product_id = sales_line.product_id.id if sales_line else None
                if not product_id:
                    continue
                product = self.env["product.product"].sudo().browse(product_id)
                if not self._is_stockable_product(product):
                    continue
                unit_id = unit_map.get(row.uomId or 0)
                quantity_shipped = row.qtyShipped or 0
                move_values: "odoo.values.stock_move" = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_shipped),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "sale_line_id": sale_line_id or False,
                }
                # noinspection DuplicatedCode
                move_line_payloads[external_id_value] = {
                    "product_id": product_id,
                    "product_uom_id": unit_id or product.uom_id.id,
                    "qty_done": float(quantity_shipped),
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
                            "resource": RESOURCE_SHIPMENT_LINE,
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

            shipment_line_processed += len(batch_rows)
            if shipment_line_processed >= shipment_line_log_threshold:
                elapsed = time.monotonic() - shipment_line_started_at
                _logger.info(
                    "Fishbowl import: shipment lines processed %s in %.2fs",
                    shipment_line_processed,
                    elapsed,
                )
                shipment_line_log_threshold += shipment_line_log_every
            self._commit_and_clear()

        if shipment_item_rows:
            shipment_elapsed = time.monotonic() - shipment_line_started_at
            _logger.info("Fishbowl import: shipment lines complete in %.2fs", shipment_elapsed)

        if done_picking_ids:
            finalize_started_at = time.monotonic()
            total_pickings = len(done_picking_ids)
            _logger.info("Fishbowl import: finalizing %s shipments", total_pickings)
            finalized_count = 0
            finalize_log_every = 500
            for picking_id in done_picking_ids:
                self._finalize_picking(picking_model.browse(picking_id))
                finalized_count += 1
                if finalized_count % finalize_log_every == 0:
                    elapsed = time.monotonic() - finalize_started_at
                    _logger.info(
                        "Fishbowl import: finalized %s/%s shipments in %.2fs",
                        finalized_count,
                        total_pickings,
                        elapsed,
                    )
                    self._commit_and_clear()
            self._commit_and_clear()
            finalize_elapsed = time.monotonic() - finalize_started_at
            _logger.info("Fishbowl import: finalized %s shipments in %.2fs", total_pickings, finalize_elapsed)
