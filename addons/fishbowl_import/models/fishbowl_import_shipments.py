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
        fishbowl_system: "odoo.model.external_system",
        sync_started_at: datetime,
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
        shipment_existing_map, _shipment_stale_map, shipment_blocked = self._prefetch_external_id_records(
            fishbowl_system.id,
            RESOURCE_SHIPMENT,
            shipment_external_ids,
            "stock.picking",
        )
        shipment_latest_dates: dict[int, datetime] = {}
        shipments_to_process: set[int] = set()
        for row in shipped_rows:
            updated_at = row.dateShipped or row.dateCreated
            if updated_at:
                shipment_latest_dates[row.id] = updated_at
            if updated_at is None or self._should_process_external_row(
                fishbowl_system,
                str(row.id),
                RESOURCE_SHIPMENT,
                updated_at,
            ):
                shipments_to_process.add(row.id)

        shipment_line_blocked: set[int] = set()
        for row in shipped_rows:
            fishbowl_id = row.id
            external_id_value = str(fishbowl_id)
            if fishbowl_id not in shipments_to_process:
                continue
            if external_id_value in shipment_blocked:
                shipment_line_blocked.add(fishbowl_id)
                continue
            existing_picking_id = shipment_existing_map.get(external_id_value)
            sale_order_id = order_maps["sales_order"].get(row.soId or 0)
            partner_id = False
            if sale_order_id:
                partner_id = self.env["sale.order"].sudo().browse(sale_order_id).partner_id.id
            values = {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "partner_id": partner_id or False,
                "origin": row.num or False,
                "sale_id": sale_order_id or False,
                "scheduled_date": row.dateShipped or row.dateCreated,
                "date_done": row.dateShipped,
            }
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
                update_values = dict(values)
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
        shipment_item_rows = self._fetch_rows_by_ids(
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
        shipment_line_batch_size = 500
        shipment_line_totals: dict[int, int] = {}
        shipment_line_success: dict[int, int] = {}
        for row in shipment_item_rows:
            ship_id = row.shipId
            if ship_id is None:
                continue
            shipment_line_totals[ship_id] = shipment_line_totals.get(ship_id, 0) + 1
        for start_index in range(0, len(shipment_item_rows), shipment_line_batch_size):
            batch_rows = shipment_item_rows[start_index : start_index + shipment_line_batch_size]
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
                RESOURCE_SHIPMENT_LINE,
                batch_rows,
            )

            for row in batch_rows:
                ship_id = row.shipId
                if ship_id is None:
                    continue
                picking_id = shipment_map.get(ship_id)
                if not picking_id:
                    shipment_line_blocked.add(ship_id)
                    continue
                fishbowl_id = row.id
                external_id_value = str(fishbowl_id)
                if external_id_value in blocked:
                    shipment_line_blocked.add(ship_id)
                    continue
                picking = picking_model.browse(picking_id)
                sales_line = self._resolve_sales_line_for_shipment_row(
                    row,
                    order_maps,
                    sales_line_external_map,
                )
                sale_line_id = sales_line.id if sales_line else False
                product_id = sales_line.product_id.id if sales_line else None
                # noinspection DuplicatedCode
                # Receipt/shipment line handling stays explicit to keep line-field differences readable.
                if not product_id:
                    shipment_line_blocked.add(ship_id)
                    continue
                product = self.env["product.product"].sudo().browse(product_id)
                if not self._is_stockable_product(product):
                    shipment_line_success[ship_id] = shipment_line_success.get(ship_id, 0) + 1
                    continue
                unit_id = unit_map.get(row.uomId or 0)
                quantity_shipped = row.qtyShipped or 0
                move_values = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_shipped),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "sale_line_id": sale_line_id or False,
                }
                # noinspection DuplicatedCode
                # Receipt/shipment move handling stays explicit to keep order-line differences readable.
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
                        processed_external_ids.append(external_id_value)
                        shipment_line_success[ship_id] = shipment_line_success.get(ship_id, 0) + 1
                        continue
                    existing_move.write(move_values)
                    batch_move_ids[external_id_value] = existing_move_id
                    processed_external_ids.append(external_id_value)
                    shipment_line_success[ship_id] = shipment_line_success.get(ship_id, 0) + 1
                    continue
                create_values.append(move_values)
                create_external_ids.append(external_id_value)
                shipment_line_success[ship_id] = shipment_line_success.get(ship_id, 0) + 1

            created_move_ids = self._create_stock_moves_with_external_ids(
                move_model,
                create_values=create_values,
                create_external_ids=create_external_ids,
                stale_map=stale_map,
                system_id=fishbowl_system.id,
                resource=RESOURCE_SHIPMENT_LINE,
            )
            for external_id_value, move_id in created_move_ids.items():
                batch_move_ids[external_id_value] = move_id
                processed_external_ids.append(external_id_value)
            if processed_external_ids:
                self._mark_external_ids_synced(
                    fishbowl_system.id,
                    RESOURCE_SHIPMENT_LINE,
                    processed_external_ids,
                    sync_started_at,
                )

            self._ensure_stock_move_lines(
                move_model,
                move_line_model,
                batch_move_ids,
                move_line_payloads,
            )

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

        if shipment_line_totals:
            synced_shipments = 0
            for ship_id, total_lines in shipment_line_totals.items():
                if ship_id in shipment_line_blocked:
                    continue
                if total_lines <= 0:
                    continue
                if shipment_line_success.get(ship_id, 0) != total_lines:
                    continue
                updated_at = shipment_latest_dates.get(ship_id) or sync_started_at
                self._mark_external_id_synced(
                    fishbowl_system,
                    str(ship_id),
                    RESOURCE_SHIPMENT,
                    updated_at,
                )
                synced_shipments += 1
            if synced_shipments:
                _logger.info("Fishbowl import: synced %s shipments", synced_shipments)

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
