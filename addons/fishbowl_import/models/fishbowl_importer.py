from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.fishbowl_client import FishbowlClient, FishbowlConnectionSettings

_logger = logging.getLogger(__name__)

EXTERNAL_SYSTEM_CODE = "fishbowl"

RESOURCE_ADDRESS = "address"
RESOURCE_CUSTOMER = "customer"
RESOURCE_VENDOR = "vendor"
RESOURCE_PART = "part"
RESOURCE_PRODUCT = "product"
RESOURCE_UNIT = "uom"
RESOURCE_SALES_ORDER = "so"
RESOURCE_SALES_ORDER_LINE = "soitem"
RESOURCE_PURCHASE_ORDER = "po"
RESOURCE_PURCHASE_ORDER_LINE = "poitem"
RESOURCE_SHIPMENT = "ship"
RESOURCE_SHIPMENT_LINE = "shipitem"
RESOURCE_RECEIPT = "receipt"
RESOURCE_RECEIPT_LINE = "receiptitem"

IMPORT_CONTEXT: dict[str, bool] = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "skip_shopify_sync": True,
    "skip_procurement": True,
}


class FishbowlImporter(models.Model):
    _name = "fishbowl.importer"
    _description = "Fishbowl Importer"

    @api.model
    def run_scheduled_import(self) -> None:
        self._run_import(update_last_sync=True)

    @api.model
    def run_full_import(self) -> None:
        self._run_import(update_last_sync=False, start_datetime=None)

    @api.model
    def _run_import(self, *, update_last_sync: bool, start_datetime: datetime | None = None) -> None:
        fishbowl_settings = self._get_fishbowl_settings()
        run_started_at = fields.Datetime.now()
        if start_datetime is None and update_last_sync:
            start_datetime = self._get_last_sync_at()
        try:
            self._get_fishbowl_system()
            with FishbowlClient(fishbowl_settings) as client:
                self._import_units_of_measure(client)
                partner_maps = self._import_partners(client)
                product_maps = self._import_products(client)
                order_maps = self._import_orders(client, partner_maps, product_maps, start_datetime)
                self._import_shipments(client, order_maps, product_maps, start_datetime)
                self._import_receipts(client, order_maps, product_maps, start_datetime)
        except Exception as exc:
            _logger.exception("Fishbowl import failed")
            self._record_last_run("failed", str(exc))
            raise
        self._record_last_run("success", "")
        if update_last_sync:
            self._set_last_sync_at(run_started_at)

    def _import_units_of_measure(self, client: FishbowlClient) -> None:
        unit_rows = client.fetch_all("SELECT id, name, code, uomType, defaultRecord, integral, activeFlag FROM uom ORDER BY id")
        conversion_rows = client.fetch_all("SELECT fromUomId, toUomId, factor, multiply FROM uomconversion ORDER BY id")
        reference_by_type: dict[int, int] = {}
        unit_ids_by_type: dict[int, list[int]] = {}
        for row in unit_rows:
            unit_type_id = int(row.get("uomType") or 0)
            unit_id = int(row.get("id") or 0)
            if unit_type_id:
                unit_ids_by_type.setdefault(unit_type_id, []).append(unit_id)
            if self._to_bool(row.get("defaultRecord")) and unit_type_id:
                reference_by_type[unit_type_id] = unit_id
        for unit_type_id, unit_ids in unit_ids_by_type.items():
            if unit_type_id not in reference_by_type and unit_ids:
                reference_by_type[unit_type_id] = unit_ids[0]

        ratios_by_id = self._compute_unit_ratios(unit_rows, conversion_rows)
        unit_model = self.env["uom.uom"].sudo().with_context(IMPORT_CONTEXT)
        reference_unit_map: dict[int, int] = {}
        for row in unit_rows:
            fishbowl_unit_id = int(row["id"])
            unit_type_id = int(row.get("uomType") or 0)
            reference_unit_id = reference_by_type.get(unit_type_id)
            if not reference_unit_id or reference_unit_id != fishbowl_unit_id:
                continue
            name = str(row.get("name") or "").strip() or f"Unit {fishbowl_unit_id}"
            values = {
                "name": name,
                "relative_factor": 1.0,
                "relative_uom_id": False,
                "active": self._to_bool(row.get("activeFlag")),
            }
            unit = unit_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_unit_id),
                values,
                RESOURCE_UNIT,
            )
            reference_unit_map[fishbowl_unit_id] = unit.id

        for row in unit_rows:
            fishbowl_unit_id = int(row["id"])
            unit_type_id = int(row.get("uomType") or 0)
            reference_unit_id = reference_by_type.get(unit_type_id)
            if not reference_unit_id:
                _logger.warning("Missing reference UoM for Fishbowl unit %s", fishbowl_unit_id)
                continue
            reference_odoo_id = reference_unit_map.get(reference_unit_id)
            if not reference_odoo_id:
                _logger.warning("Missing reference mapping for Fishbowl unit %s", fishbowl_unit_id)
                continue
            name = str(row.get("name") or "").strip() or f"Unit {fishbowl_unit_id}"
            ratio = ratios_by_id.get(fishbowl_unit_id)
            if ratio is None:
                ratio = 1.0
                _logger.warning("Missing conversion ratio for Fishbowl unit %s; defaulting to 1.0", fishbowl_unit_id)
            values = {
                "name": name,
                "relative_factor": float(ratio),
                "relative_uom_id": reference_odoo_id,
                "active": self._to_bool(row.get("activeFlag")),
            }
            if fishbowl_unit_id == reference_unit_id:
                values["relative_factor"] = 1.0
                values["relative_uom_id"] = False
            unit_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_unit_id),
                values,
                RESOURCE_UNIT,
            )

    def _import_partners(self, client: FishbowlClient) -> dict[str, dict[int, int]]:
        customer_rows = client.fetch_all("SELECT id, accountId, number, name, note, activeFlag FROM customer ORDER BY id")
        vendor_rows = client.fetch_all("SELECT id, accountId, name, accountNum, note, activeFlag FROM vendor ORDER BY id")
        address_rows = client.fetch_all(
            "SELECT id, accountId, name, addressName, address, city, stateId, countryId, zip, typeId FROM address ORDER BY id"
        )
        address_type_rows = client.fetch_all("SELECT id, name FROM addresstype ORDER BY id")
        country_rows = client.fetch_all("SELECT id, name, abbreviation FROM countryconst ORDER BY id")
        state_rows = client.fetch_all("SELECT id, countryConstID, name, code FROM stateconst ORDER BY id")

        address_type_map = {int(row["id"]): str(row["name"]).strip() for row in address_type_rows}
        country_map = {int(row["id"]): row for row in country_rows}
        state_map = {int(row["id"]): row for row in state_rows}

        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        account_partner_map: dict[int, int] = {}
        customer_partner_map: dict[int, int] = {}
        vendor_partner_map: dict[int, int] = {}

        for row in customer_rows:
            fishbowl_id = int(row["id"])
            values = {
                "name": str(row["name"]).strip() or f"Customer {fishbowl_id}",
                "ref": str(row.get("number") or "").strip() or False,
                "comment": row.get("note") or False,
                "active": self._to_bool(row.get("activeFlag")),
                "customer_rank": 1,
            }
            partner = partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_CUSTOMER,
            )
            account_id = row.get("accountId")
            if account_id is not None:
                account_partner_map[int(account_id)] = partner.id
            customer_partner_map[fishbowl_id] = partner.id

        for row in vendor_rows:
            fishbowl_id = int(row["id"])
            values = {
                "name": str(row["name"]).strip() or f"Vendor {fishbowl_id}",
                "ref": str(row.get("accountNum") or "").strip() or False,
                "comment": row.get("note") or False,
                "active": self._to_bool(row.get("activeFlag")),
                "supplier_rank": 1,
            }
            partner = partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_VENDOR,
            )
            account_id = row.get("accountId")
            if account_id is not None:
                account_partner_map.setdefault(int(account_id), partner.id)
            vendor_partner_map[fishbowl_id] = partner.id

        address_type_mapping = {
            "ship to": "delivery",
            "bill to": "invoice",
            "remit to": "invoice",
            "home": "other",
            "main office": "contact",
        }

        for row in address_rows:
            fishbowl_id = int(row["id"])
            account_id = row.get("accountId")
            if account_id is None:
                continue
            parent_id = account_partner_map.get(int(account_id))
            if not parent_id:
                continue
            address_type_name = address_type_map.get(int(row.get("typeId") or 0), "")
            partner_type = address_type_mapping.get(address_type_name.lower(), "other")
            country_id = self._resolve_country_id(row.get("countryId"), country_map)
            state_id = self._resolve_state_id(row.get("stateId"), state_map, country_map, country_id)
            values = {
                "parent_id": parent_id,
                "type": partner_type,
                "name": str(row.get("addressName") or row.get("name") or "").strip() or False,
                "street": str(row.get("address") or "").strip() or False,
                "city": str(row.get("city") or "").strip() or False,
                "zip": str(row.get("zip") or "").strip() or False,
                "country_id": country_id or False,
                "state_id": state_id or False,
            }
            partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_ADDRESS,
            )

        return {
            "account": account_partner_map,
            "customer": customer_partner_map,
            "vendor": vendor_partner_map,
        }

    def _import_products(self, client: FishbowlClient) -> dict[str, dict[int, int]]:
        part_type_rows = client.fetch_all("SELECT id, name FROM parttype ORDER BY id")
        part_type_map = {int(row["id"]): str(row["name"]).strip().lower() for row in part_type_rows}
        part_rows = client.fetch_all(
            "SELECT id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag "
            "FROM part ORDER BY id"
        )
        product_rows = client.fetch_all("SELECT id, partId, num, description, price, uomId, activeFlag FROM product ORDER BY id")

        unit_map = self._load_unit_map()
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)

        part_product_map: dict[int, int] = {}
        product_product_map: dict[int, int] = {}

        for row in part_rows:
            fishbowl_id = int(row["id"])
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            part_type_name = part_type_map.get(int(row.get("typeId") or 0), "")
            product_type = self._map_part_type(part_type_name)
            values = {
                "name": str(row.get("description") or row.get("num") or "").strip() or f"Part {fishbowl_id}",
                "default_code": str(row.get("num") or "").strip() or False,
                "description": row.get("details") or False,
                "active": self._to_bool(row.get("activeFlag")),
                "sale_ok": False,
                "purchase_ok": product_type in {"product", "consu"},
                "tracking": self._map_tracking(row.get("trackingFlag"), row.get("serializedFlag")),
            }
            if unit_id:
                values["uom_id"] = unit_id
            values[self._product_type_field(template_model)] = product_type
            standard_price = row.get("stdCost")
            if standard_price is not None:
                values["standard_price"] = float(standard_price)
            template = template_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PART,
            )
            part_product_map[fishbowl_id] = template.product_variant_id.id

        for row in product_rows:
            fishbowl_id = int(row["id"])
            part_id = row.get("partId")
            if part_id is None:
                continue
            variant_id = part_product_map.get(int(part_id))
            if not variant_id:
                continue
            variant = self.env["product.product"].browse(variant_id)
            template = template_model.browse(variant.product_tmpl_id.id)
            values: dict[str, Any] = {
                "name": str(row.get("description") or row.get("num") or template.name).strip(),
                "active": self._to_bool(row.get("activeFlag")),
                "sale_ok": True,
            }
            list_price = row.get("price")
            if list_price is not None:
                values["list_price"] = float(list_price)
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            if unit_id:
                values["uom_id"] = unit_id
            self._write_if_changed(template, values)
            template.set_external_id(EXTERNAL_SYSTEM_CODE, str(fishbowl_id), RESOURCE_PRODUCT)
            product_product_map[fishbowl_id] = variant_id

        return {
            "part": part_product_map,
            "product": product_product_map,
        }

    def _import_orders(
        self,
        client: FishbowlClient,
        partner_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> dict[str, dict[int, int]]:
        sales_status_map = self._load_status_map(client, "sostatus")
        purchase_status_map = self._load_status_map(client, "postatus")

        sales_order_rows = self._fetch_orders(
            client,
            "so",
            "dateIssued",
            start_datetime,
        )
        sales_order_ids = [int(row["id"]) for row in sales_order_rows]
        sales_line_rows = self._fetch_rows_by_ids(
            client,
            "soitem",
            "soId",
            sales_order_ids,
            select_columns="id, soId, productId, productNum, description, qtyOrdered, unitPrice, uomId",
        )
        purchase_order_rows = self._fetch_orders(
            client,
            "po",
            "dateIssued",
            start_datetime,
        )
        purchase_order_ids = [int(row["id"]) for row in purchase_order_rows]
        purchase_line_rows = self._fetch_rows_by_ids(
            client,
            "poitem",
            "poId",
            purchase_order_ids,
            select_columns="id, poId, partId, partNum, description, qtyToFulfill, unitCost, uomId",
        )

        unit_map = self._load_unit_map()
        sale_order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        sale_line_model = self.env["sale.order.line"].sudo().with_context(IMPORT_CONTEXT)
        purchase_order_model = self.env["purchase.order"].sudo().with_context(IMPORT_CONTEXT)
        purchase_line_model = self.env["purchase.order.line"].sudo().with_context(IMPORT_CONTEXT)

        sales_order_map: dict[int, int] = {}
        sales_line_map: dict[int, int] = {}
        purchase_order_map: dict[int, int] = {}
        purchase_line_map: dict[int, int] = {}

        for row in sales_order_rows:
            fishbowl_id = int(row["id"])
            partner_id = partner_maps["customer"].get(int(row["customerId"]))
            if not partner_id:
                continue
            order_state = self._map_sales_state(sales_status_map.get(int(row.get("statusId") or 0), ""))
            values = {
                "name": str(row.get("num") or f"SO-{fishbowl_id}"),
                "partner_id": partner_id,
                "partner_invoice_id": partner_id,
                "partner_shipping_id": partner_id,
                "date_order": row.get("dateIssued") or row.get("dateCreated"),
                "client_order_ref": row.get("customerPO") or False,
                "note": row.get("note") or False,
                "state": order_state,
            }
            order = sale_order_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_SALES_ORDER,
            )
            sales_order_map[fishbowl_id] = order.id

        for row in sales_line_rows:
            fishbowl_id = int(row["id"])
            order_id = sales_order_map.get(int(row["soId"]))
            if not order_id:
                continue
            product_id = self._resolve_product_from_sales_row(row, product_maps)
            if not product_id:
                _logger.warning("Missing product for Fishbowl soitem %s; skipping line", row.get("id"))
                continue
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            quantity_ordered = row.get("qtyOrdered") or 0
            unit_price = row.get("unitPrice") or 0
            values = {
                "order_id": order_id,
                "product_id": product_id or False,
                "name": row.get("description") or False,
                "product_uom_qty": float(quantity_ordered),
                "price_unit": float(unit_price),
            }
            if unit_id:
                values["product_uom"] = unit_id
            line = sale_line_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_SALES_ORDER_LINE,
            )
            sales_line_map[fishbowl_id] = line.id

        for row in purchase_order_rows:
            fishbowl_id = int(row["id"])
            partner_id = partner_maps["vendor"].get(int(row["vendorId"]))
            if not partner_id:
                continue
            order_state = self._map_purchase_state(purchase_status_map.get(int(row.get("statusId") or 0), ""))
            values = {
                "name": str(row.get("num") or f"PO-{fishbowl_id}"),
                "partner_id": partner_id,
                "date_order": row.get("dateIssued") or row.get("dateCreated"),
                "notes": row.get("note") or False,
                "state": order_state,
            }
            order = purchase_order_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PURCHASE_ORDER,
            )
            purchase_order_map[fishbowl_id] = order.id

        for row in purchase_line_rows:
            fishbowl_id = int(row["id"])
            order_id = purchase_order_map.get(int(row["poId"]))
            if not order_id:
                continue
            part_id = row.get("partId")
            product_id = product_maps["part"].get(int(part_id)) if part_id is not None else None
            if not product_id:
                _logger.warning("Missing product for Fishbowl poitem %s; skipping line", row.get("id"))
                continue
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            quantity_ordered = row.get("qtyToFulfill") or 0
            unit_cost = row.get("unitCost") or 0
            values = {
                "order_id": order_id,
                "product_id": product_id or False,
                "name": row.get("description") or False,
                "product_qty": float(quantity_ordered),
                "price_unit": float(unit_cost),
            }
            if unit_id:
                values["product_uom"] = unit_id
            line = purchase_line_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PURCHASE_ORDER_LINE,
            )
            purchase_line_map[fishbowl_id] = line.id

        return {
            "sales_order": sales_order_map,
            "sales_line": sales_line_map,
            "purchase_order": purchase_order_map,
            "purchase_line": purchase_line_map,
        }

    def _import_shipments(
        self,
        client: FishbowlClient,
        order_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> None:
        shipment_rows = self._fetch_orders(
            client,
            "ship",
            "dateShipped",
            start_datetime,
            extra_where="dateShipped IS NOT NULL",
        )
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
        done_pickings: list[models.Model] = []

        for row in shipment_rows:
            fishbowl_id = int(row["id"])
            sale_order_id = order_maps["sales_order"].get(int(row.get("soId") or 0))
            partner_id = False
            if sale_order_id:
                partner_id = self.env["sale.order"].sudo().browse(sale_order_id).partner_id.id
            status_name = shipment_status_map.get(int(row.get("statusId") or 0), "")
            if status_name.lower() != "shipped":
                continue
            values = {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "partner_id": partner_id or False,
                "origin": row.get("num") or False,
                "sale_id": sale_order_id or False,
                "scheduled_date": row.get("dateShipped") or row.get("dateCreated"),
                "date_done": row.get("dateShipped"),
            }
            picking = picking_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_SHIPMENT,
            )
            shipment_map[fishbowl_id] = picking.id
            done_pickings.append(picking)

        if not shipment_map:
            return
        shipment_item_rows = self._fetch_rows_by_ids(
            client,
            "shipitem",
            "shipId",
            list(shipment_map.keys()),
            select_columns="id, shipId, soItemId, qtyShipped, uomId",
        )
        missing_sales_line_ids = {
            int(row["soItemId"])
            for row in shipment_item_rows
            if row.get("soItemId") is not None
            and int(row["soItemId"]) not in order_maps["sales_line"]
        }
        sales_line_external_map: dict[int, int] = {}
        if missing_sales_line_ids:
            fishbowl_system = self._get_fishbowl_system()
            external_id_records = self.env["external.id"].sudo().search(
                [
                    ("system_id", "=", fishbowl_system.id),
                    ("resource", "=", RESOURCE_SALES_ORDER_LINE),
                    ("res_model", "=", "sale.order.line"),
                    ("active", "=", True),
                    ("external_id", "in", [str(value) for value in missing_sales_line_ids]),
                ]
            )
            for record in external_id_records:
                try:
                    sales_line_external_map[int(record.external_id)] = record.res_id
                except (TypeError, ValueError):
                    _logger.warning("Invalid Fishbowl sales line external id '%s'", record.external_id)
        unit_map = self._load_unit_map()
        for row in shipment_item_rows:
            ship_id = row.get("shipId")
            if ship_id is None:
                continue
            picking_id = shipment_map.get(int(ship_id))
            if not picking_id:
                continue
            fishbowl_id = int(row["id"])
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
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            quantity_shipped = row.get("qtyShipped") or 0
            move_values = {
                "name": picking.name,
                "product_id": product_id,
                "product_uom_qty": float(quantity_shipped),
                "product_uom": unit_id or self.env["product.product"].browse(product_id).uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
                "sale_line_id": sale_line_id or False,
            }
            move = move_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                move_values,
                RESOURCE_SHIPMENT_LINE,
            )
            if move.move_line_ids:
                continue
            move_line_model.create(
                {
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "qty_done": float(quantity_shipped),
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                }
            )

        for picking in done_pickings:
            self._finalize_picking(picking)

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
            status_id
            for status_id, status_name in receipt_status_map.items()
            if status_name.lower() in done_statuses
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
        receipt_conditions = [f"ri.dateReceived IS NOT NULL", f"r.statusId IN ({status_placeholders})"]
        receipt_params: list[Any] = list(done_status_ids)
        if start_datetime:
            receipt_conditions.append("ri.dateReceived >= %s")
            receipt_params.append(start_datetime)
        receipt_where = " AND ".join(receipt_conditions)
        receipt_query = (
            "SELECT ri.id, ri.receiptId, ri.poItemId, ri.qty, ri.uomId, ri.dateReceived, ri.partId, r.poId "
            "FROM receiptitem ri JOIN receipt r ON r.id = ri.receiptId "
            f"WHERE {receipt_where} ORDER BY ri.id"
        )
        receipt_item_rows = client.fetch_all(receipt_query, receipt_params)

        unit_map = self._load_unit_map()
        done_pickings: dict[int, models.Model] = {}

        for row in receipt_item_rows:
            receipt_id = row.get("receiptId")
            if receipt_id is None:
                continue
            fishbowl_receipt_id = int(receipt_id)
            picking = done_pickings.get(fishbowl_receipt_id)
            if not picking:
                purchase_order_id = order_maps["purchase_order"].get(int(row.get("poId") or 0))
                partner_id = False
                if purchase_order_id:
                    partner_id = self.env["purchase.order"].sudo().browse(purchase_order_id).partner_id.id
                values = {
                    "picking_type_id": picking_type.id,
                    "location_id": source_location.id,
                    "location_dest_id": destination_location.id,
                    "partner_id": partner_id or False,
                    "origin": row.get("receiptId"),
                    "purchase_id": purchase_order_id or False,
                    "scheduled_date": row.get("dateReceived"),
                    "date_done": row.get("dateReceived"),
                }
                picking = picking_model.get_or_create_by_external_id(
                    EXTERNAL_SYSTEM_CODE,
                    str(fishbowl_receipt_id),
                    values,
                    RESOURCE_RECEIPT,
                )
                done_pickings[fishbowl_receipt_id] = picking

            fishbowl_line_id = int(row["id"])
            product_id = self._resolve_product_from_receipt_row(row, order_maps, product_maps)
            if not product_id:
                continue
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            quantity_received = row.get("qty") or 0
            move_values = {
                "name": picking.name,
                "product_id": product_id,
                "product_uom_qty": float(quantity_received),
                "product_uom": unit_id or self.env["product.product"].browse(product_id).uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
                "purchase_line_id": order_maps["purchase_line"].get(int(row.get("poItemId") or 0)) or False,
            }
            move = move_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_line_id),
                move_values,
                RESOURCE_RECEIPT_LINE,
            )
            if move.move_line_ids:
                continue
            move_line_model.create(
                {
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "qty_done": float(quantity_received),
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                }
            )

        for picking in done_pickings.values():
            self._finalize_picking(picking)

    def _get_fishbowl_settings(self) -> FishbowlConnectionSettings:
        host = self._get_config_value("fishbowl.host", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__HOST")
        user = self._get_config_value("fishbowl.user", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__USER")
        database = self._get_config_value("fishbowl.db", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__DB")
        password = self._get_config_value("fishbowl.password", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__PASSWORD")
        port_raw = self._get_config_value("fishbowl.port", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__PORT", required=False)
        port = int(port_raw) if port_raw else 3306
        ssl_verify = self._get_config_bool(
            "fishbowl.ssl_verify",
            "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__SSL_VERIFY",
            default=True,
        )
        if not host or not user or not database or not password:
            raise UserError("Fishbowl connection settings are missing.")
        if not ssl_verify:
            _logger.warning("Fishbowl SSL verification disabled; enable for production.")
        return FishbowlConnectionSettings(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            ssl_verify=ssl_verify,
        )

    def _get_config_value(self, key: str, env_key: str, *, required: bool = True) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if required and not value:
            raise UserError(f"Missing configuration for {key}.")
        return value

    def _get_config_bool(self, key: str, env_key: str, *, default: bool) -> bool:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if not value:
            return default
        return self._to_bool(value)

    def _get_last_sync_at(self) -> datetime | None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param("fishbowl.last_sync_at")
        if not value:
            return None
        try:
            return fields.Datetime.from_string(value)
        except Exception:
            return None

    def _set_last_sync_at(self, value: datetime) -> None:
        self.env["ir.config_parameter"].sudo().set_param("fishbowl.last_sync_at", fields.Datetime.to_string(value))

    def _record_last_run(self, status: str, message: str) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("fishbowl.last_run_status", status)
        parameter_model.set_param("fishbowl.last_run_message", message)
        parameter_model.set_param("fishbowl.last_run_at", fields.Datetime.to_string(fields.Datetime.now()))

    def _finalize_picking(self, picking: models.Model) -> None:
        target_date = picking.date_done or picking.scheduled_date or fields.Datetime.now()
        try:
            picking.with_context(force_period_date=target_date)._action_done()
        except Exception:
            _logger.exception("Failed to finalize picking %s", picking.name)
            return
        updates: dict[str, Any] = {}
        if "date_done" in picking._fields:
            updates["date_done"] = target_date
        if updates:
            picking.write(updates)
        move_updates: dict[str, Any] = {}
        if "date" in picking.move_ids._fields:
            move_updates["date"] = target_date
        if move_updates:
            picking.move_ids.write(move_updates)
        line_updates: dict[str, Any] = {}
        if "date" in picking.move_line_ids._fields:
            line_updates["date"] = target_date
        if line_updates:
            picking.move_line_ids.write(line_updates)

    def _get_fishbowl_system(self) -> models.Model:
        system = self.env["external.system"].sudo().search([("code", "=", EXTERNAL_SYSTEM_CODE)], limit=1)
        if not system:
            raise UserError("External system 'fishbowl' is not configured.")
        return system

    def _write_if_changed(self, record: models.Model, values: dict[str, Any]) -> None:
        changes: dict[str, Any] = {}
        for field_name, value in values.items():
            if field_name not in record._fields:
                continue
            current_value = record[field_name]
            if isinstance(current_value, models.BaseModel):
                current_value = current_value.id
            if current_value != value:
                changes[field_name] = value
        if changes:
            record.write(changes)

    def _load_status_map(self, client: FishbowlClient, table: str) -> dict[int, str]:
        rows = client.fetch_all(f"SELECT id, name FROM {table} ORDER BY id")
        return {int(row["id"]): str(row["name"]).strip() for row in rows}

    def _map_sales_state(self, status_name: str) -> str:
        mapping = {
            "estimate": "draft",
            "issued": "sale",
            "in progress": "sale",
            "fulfilled": "sale",
            "closed short": "sale",
            "voided": "cancel",
            "cancelled": "cancel",
            "expired": "cancel",
            "historical": "sale",
        }
        return mapping.get(status_name.lower(), "draft")

    def _map_purchase_state(self, status_name: str) -> str:
        mapping = {
            "bid request": "draft",
            "pending approval": "to approve",
            "issued": "purchase",
            "picking": "purchase",
            "partial": "purchase",
            "picked": "purchase",
            "shipped": "purchase",
            "fulfilled": "purchase",
            "closed short": "purchase",
            "void": "cancel",
            "historical": "purchase",
        }
        return mapping.get(status_name.lower(), "draft")

    def _map_part_type(self, part_type_name: str) -> str:
        mapping = {
            "inventory": "consu",
            "service": "service",
            "labor": "service",
            "overhead": "service",
            "non-inventory": "consu",
            "internal use": "consu",
            "capital equipment": "consu",
            "shipping": "consu",
            "tax": "consu",
            "misc": "consu",
        }
        return mapping.get(part_type_name.lower(), "consu")

    def _map_tracking(self, tracking_flag: Any, serialized_flag: Any) -> str:
        if self._to_bool(serialized_flag):
            return "serial"
        if self._to_bool(tracking_flag):
            return "lot"
        return "none"

    def _to_bool(self, value: Any) -> bool:
        if value in (True, False):
            return bool(value)
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        value_str = str(value).strip().lower()
        return value_str in {"1", "true", "yes", "on", "y", "t"}

    def _resolve_country_id(self, country_id: Any, country_map: dict[int, dict[str, Any]]) -> int | None:
        if not country_id:
            return None
        country_record = country_map.get(int(country_id))
        if not country_record:
            return None
        code = str(country_record.get("abbreviation") or "").strip()
        if not code:
            return None
        country = self.env["res.country"].sudo().search([("code", "=", code)], limit=1)
        return country.id if country else None

    def _resolve_state_id(
        self,
        state_id: Any,
        state_map: dict[int, dict[str, Any]],
        country_map: dict[int, dict[str, Any]],
        country_id: int | None,
    ) -> int | None:
        if not state_id:
            return None
        state_record = state_map.get(int(state_id))
        if not state_record:
            return None
        code = str(state_record.get("code") or "").strip()
        if not code:
            return None
        domain = [("code", "=", code)]
        if country_id:
            domain.append(("country_id", "=", country_id))
        state = self.env["res.country.state"].sudo().search(domain, limit=1)
        if state:
            return state.id
        country_record = country_map.get(int(state_record.get("countryConstID") or 0))
        if not country_record:
            return None
        country_code = str(country_record.get("abbreviation") or "").strip()
        if not country_code:
            return None
        country = self.env["res.country"].sudo().search([("code", "=", country_code)], limit=1)
        if not country:
            return None
        state = (
            self.env["res.country.state"]
            .sudo()
            .search(
                [("code", "=", code), ("country_id", "=", country.id)],
                limit=1,
            )
        )
        return state.id if state else None

    def _product_type_field(self, template_model: models.Model) -> str:
        return "detailed_type" if "detailed_type" in template_model._fields else "type"

    def _load_unit_map(self) -> dict[int, int]:
        unit_map: dict[int, int] = {}
        external_id_model = self.env["external.id"].sudo()
        fishbowl_system = self._get_fishbowl_system()
        unit_records = external_id_model.search(
            [
                ("system_id", "=", fishbowl_system.id),
                ("resource", "=", "uom"),
                ("res_model", "=", "uom.uom"),
            ]
        )
        for record in unit_records:
            unit_map[int(record.external_id)] = record.res_id
        if unit_map:
            return unit_map

        unit_rows = self.env["uom.uom"].sudo().search([])
        for unit in unit_rows:
            unit_map[int(unit.id)] = unit.id
        return unit_map

    def _compute_unit_ratios(self, unit_rows: list[dict[str, Any]], conversion_rows: list[dict[str, Any]]) -> dict[int, float]:
        reference_by_type: dict[int, int] = {}
        unit_ids_by_type: dict[int, list[int]] = {}
        for row in unit_rows:
            unit_type_id = int(row.get("uomType") or 0)
            unit_id = int(row.get("id") or 0)
            if unit_type_id:
                unit_ids_by_type.setdefault(unit_type_id, []).append(unit_id)
            if self._to_bool(row.get("defaultRecord")) and unit_type_id:
                reference_by_type[unit_type_id] = unit_id

        for unit_type_id, unit_ids in unit_ids_by_type.items():
            if unit_type_id not in reference_by_type and unit_ids:
                reference_by_type[unit_type_id] = unit_ids[0]

        adjacency: dict[int, list[tuple[int, float]]] = {}
        for row in conversion_rows:
            from_id = int(row["fromUomId"])
            to_id = int(row["toUomId"])
            factor = float(row.get("factor") or 1)
            multiply = float(row.get("multiply") or 1)
            if factor == 0:
                continue
            ratio = multiply / factor
            adjacency.setdefault(from_id, []).append((to_id, ratio))
            adjacency.setdefault(to_id, []).append((from_id, 1 / ratio))

        ratios: dict[int, float] = {}
        for unit_type_id, reference_id in reference_by_type.items():
            ratios[reference_id] = 1.0
            queue: list[int] = [reference_id]
            while queue:
                current_id = queue.pop(0)
                current_ratio = ratios[current_id]
                for neighbor_id, neighbor_ratio in adjacency.get(current_id, []):
                    if neighbor_id in ratios:
                        continue
                    ratios[neighbor_id] = current_ratio * neighbor_ratio
                    queue.append(neighbor_id)

        return ratios

    def _fetch_orders(
        self,
        client: FishbowlClient,
        table: str,
        date_column: str,
        start_datetime: datetime | None,
        *,
        extra_where: str | None = None,
        select_columns: str | None = None,
    ) -> list[dict[str, Any]]:
        columns = select_columns or "*"
        conditions: list[str] = []
        params: list[Any] = []
        if start_datetime is not None:
            conditions.append(f"{date_column} >= %s")
            params.append(start_datetime)
        if extra_where:
            conditions.append(extra_where)
        where_clause = ""
        if conditions:
            where_clause = f" WHERE {' AND '.join(conditions)}"
        query = f"SELECT {columns} FROM {table}{where_clause} ORDER BY id"
        return client.fetch_all(query, params)

    def _fetch_rows_by_ids(
        self,
        client: FishbowlClient,
        table: str,
        id_column: str,
        record_ids: list[int],
        *,
        select_columns: str | None = None,
        batch_size: int = 1000,
        extra_where: str | None = None,
        extra_params: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not record_ids:
            return []
        columns = select_columns or "*"
        results: list[dict[str, Any]] = []
        deduped_ids = sorted(set(record_ids))
        for start_index in range(0, len(deduped_ids), batch_size):
            batch_ids = deduped_ids[start_index : start_index + batch_size]
            placeholders = ", ".join(["%s"] * len(batch_ids))
            query = f"SELECT {columns} FROM {table} WHERE {id_column} IN ({placeholders})"
            params: list[Any] = list(batch_ids)
            if extra_where:
                query = f"{query} AND {extra_where}"
                if extra_params:
                    params.extend(extra_params)
            query = f"{query} ORDER BY id"
            results.extend(client.fetch_all(query, params))
        return results

    def _resolve_product_from_sales_row(self, row: dict[str, Any], product_maps: dict[str, dict[int, int]]) -> int | None:
        product_id = row.get("productId")
        if product_id is not None and int(product_id) in product_maps["product"]:
            return product_maps["product"][int(product_id)]
        product_number = str(row.get("productNum") or "").strip()
        if product_number:
            product = self.env["product.product"].sudo().search([("default_code", "=", product_number)], limit=1)
            if product:
                return product.id
        return None

    def _resolve_sales_line_for_shipment_row(
        self,
        row: dict[str, Any],
        order_maps: dict[str, dict[int, int]],
        sales_line_external_map: dict[int, int] | None = None,
    ) -> models.Model:
        sales_order_item_value = row.get("soItemId")
        if sales_order_item_value is None:
            return self.env["sale.order.line"].browse()
        sales_order_item_id = int(sales_order_item_value)
        sales_order_line_id = order_maps["sales_line"].get(sales_order_item_id)
        if not sales_order_line_id and sales_line_external_map:
            sales_order_line_id = sales_line_external_map.get(sales_order_item_id)
        if not sales_order_line_id:
            return self.env["sale.order.line"].browse()
        return self.env["sale.order.line"].sudo().browse(sales_order_line_id).exists()

    def _resolve_product_from_receipt_row(
        self,
        row: dict[str, Any],
        order_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
    ) -> int | None:
        purchase_line_id = order_maps["purchase_line"].get(int(row.get("poItemId") or 0))
        if purchase_line_id:
            return self.env["purchase.order.line"].sudo().browse(purchase_line_id).product_id.id
        part_id = row.get("partId")
        if part_id is not None:
            return product_maps["part"].get(int(part_id))
        return None

    def _get_picking_type(self, code: str) -> models.Model | None:
        picking_type = self.env["stock.picking.type"].sudo().search([("code", "=", code)], limit=1)
        return picking_type if picking_type else None

    def _get_location(self, usage: str) -> models.Model:
        location = self.env["stock.location"].sudo().search([("usage", "=", usage)], limit=1)
        if not location:
            raise UserError(f"No stock location found for usage '{usage}'.")
        return location
