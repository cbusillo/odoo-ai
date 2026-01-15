from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Iterator

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero
from psycopg2 import errors as psycopg2_errors

from ..services.fishbowl_client import FishbowlClient, FishbowlConnectionSettings, chunked

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

LEGACY_BUCKET_SHIPPING = "shipping"
LEGACY_BUCKET_FEE = "fee"
LEGACY_BUCKET_DISCOUNT = "discount"
LEGACY_BUCKET_MISC = "misc"
LEGACY_BUCKET_ADHOC = "adhoc"

IMPORT_CONTEXT: dict[str, bool] = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
    "sale_no_log_for_new_lines": True,
    "skip_shopify_sync": True,
    "skip_procurement": True,
}


# noinspection SqlResolve
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
        max_retries = int(os.environ.get("FISHBOWL_IMPORT_SERIALIZATION_RETRIES", "3"))
        retry_sleep = float(os.environ.get("FISHBOWL_IMPORT_SERIALIZATION_SLEEP", "5"))
        attempt = 0
        while True:
            try:
                self._get_fishbowl_system()
                with FishbowlClient(fishbowl_settings) as client:
                    total_started_at = time.monotonic()
                    phase_started_at = time.monotonic()
                    self._import_units_of_measure(client)
                    _logger.info("Fishbowl import: units in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    partner_maps = self._import_partners(client)
                    _logger.info("Fishbowl import: partners in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    product_maps = self._import_products(client)
                    _logger.info("Fishbowl import: products in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    order_maps = self._import_orders(client, partner_maps, product_maps, start_datetime)
                    _logger.info("Fishbowl import: orders in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_shipments(client, order_maps, product_maps, start_datetime)
                    _logger.info("Fishbowl import: shipments in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_receipts(client, order_maps, product_maps, start_datetime)
                    _logger.info("Fishbowl import: receipts in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_on_hand(client, product_maps)
                    _logger.info("Fishbowl import: on-hand in %.2fs", time.monotonic() - phase_started_at)
                    _logger.info("Fishbowl import: total in %.2fs", time.monotonic() - total_started_at)
                break
            except psycopg2_errors.SerializationFailure as exc:
                attempt += 1
                self.env.cr.rollback()
                self.env.clear()
                if attempt > max_retries:
                    _logger.exception("Fishbowl import failed after %s serialization retries", max_retries)
                    self._record_last_run("failed", str(exc))
                    raise
                sleep_for = retry_sleep * attempt
                _logger.warning(
                    "Fishbowl import serialization failure; retrying %s/%s in %.1fs",
                    attempt,
                    max_retries,
                    sleep_for,
                )
                time.sleep(sleep_for)
                continue
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
        part_type_map = self._load_part_type_map(client)
        part_rows = client.fetch_all(
            "SELECT id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag "
            "FROM part ORDER BY id"
        )
        product_rows = client.fetch_all("SELECT id, partId, num, description, price, uomId, activeFlag FROM product ORDER BY id")

        part_ids = [int(row["id"]) for row in part_rows]
        part_cost_map = self._load_part_cost_map(client, part_ids)
        sales_price_map = self._load_sales_price_map(client, product_rows)

        unit_map = self._load_unit_map()
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)

        part_product_map: dict[int, int] = {}
        product_product_map: dict[int, int] = {}

        self._upsert_part_rows(
            part_rows,
            part_type_map,
            unit_map,
            part_cost_map,
            sales_price_map,
            template_model,
            part_product_map,
        )
        self._upsert_product_rows(
            product_rows,
            unit_map,
            sales_price_map,
            template_model,
            part_product_map,
            product_product_map,
        )

        return {
            "part": part_product_map,
            "product": product_product_map,
        }

    def _load_part_type_map(self, client: FishbowlClient) -> dict[int, str]:
        part_type_rows = client.fetch_all("SELECT id, name FROM parttype ORDER BY id")
        return {int(row["id"]): str(row["name"]).strip().lower() for row in part_type_rows}

    def _upsert_part_rows(
        self,
        part_rows: list[dict[str, Any]],
        part_type_map: dict[int, str],
        unit_map: dict[int, int],
        part_cost_map: dict[int, float],
        part_price_map: dict[int, float],
        template_model: models.Model,
        part_product_map: dict[int, int],
    ) -> None:
        for row in part_rows:
            fishbowl_id = int(row["id"])
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            part_type_name = part_type_map.get(int(row.get("typeId") or 0), "")
            product_type = self._map_part_type(part_type_name)
            values = {
                "name": str(row.get("description") or row.get("num") or "").strip() or f"Part {fishbowl_id}",
                "default_code": str(row.get("num") or "").strip() or False,
                "description": row.get("details") or False,
                "active": True,
                "sale_ok": True,
                "purchase_ok": product_type in {"product", "consu"},
                "tracking": self._map_tracking(row.get("trackingFlag"), row.get("serializedFlag")),
            }
            if unit_id:
                values["uom_id"] = unit_id
            values[self._product_type_field(template_model)] = product_type
            if "is_storable" in template_model._fields:
                values["is_storable"] = product_type != "service"
            standard_price = part_cost_map.get(fishbowl_id)
            if standard_price is None:
                standard_price = row.get("stdCost")
            list_price = part_price_map.get(fishbowl_id)
            if list_price is not None and float(list_price) != 0:
                values["list_price"] = float(list_price)
            template = template_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PART,
            )
            if standard_price is not None and float(standard_price) != 0 and template.product_variant_id:
                variant = template.product_variant_id.sudo().with_context(IMPORT_CONTEXT)
                self._write_if_changed(variant, {"standard_price": float(standard_price)})
            part_product_map[fishbowl_id] = template.product_variant_id.id

    def _upsert_product_rows(
        self,
        product_rows: list[dict[str, Any]],
        unit_map: dict[int, int],
        part_price_map: dict[int, float],
        template_model: models.Model,
        part_product_map: dict[int, int],
        product_product_map: dict[int, int],
    ) -> None:
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
                "active": True,
                "sale_ok": True,
            }
            if "is_storable" in template._fields:
                values["is_storable"] = template.type != "service"
            list_price = row.get("price")
            if list_price is None or float(list_price) == 0:
                fallback_price = part_price_map.get(int(part_id))
                if fallback_price is not None:
                    list_price = fallback_price
            if list_price is not None and float(list_price) != 0:
                values["list_price"] = float(list_price)
            unit_id = unit_map.get(int(row.get("uomId") or 0))
            if unit_id:
                values["uom_id"] = unit_id
            self._write_if_changed(template, values)
            template.set_external_id(EXTERNAL_SYSTEM_CODE, str(fishbowl_id), RESOURCE_PRODUCT)
            product_product_map[fishbowl_id] = variant_id

    def _import_missing_products(
        self,
        client: FishbowlClient,
        missing_product_ids: set[int],
        part_type_map: dict[int, str],
        unit_map: dict[int, int],
        product_maps: dict[str, dict[int, int]],
        product_code_map: dict[str, int],
    ) -> set[int]:
        if not missing_product_ids:
            return set()
        product_rows = self._fetch_rows_by_ids(
            client,
            "product",
            "id",
            list(missing_product_ids),
            select_columns="id, partId, num, description, price, uomId, activeFlag",
        )
        if not product_rows:
            return set()
        part_ids: list[int] = []
        for row in product_rows:
            part_id = row.get("partId")
            if part_id is None:
                continue
            part_ids.append(int(part_id))
        missing_part_ids = [part_id for part_id in part_ids if part_id not in product_maps["part"]]
        part_rows = self._fetch_rows_by_ids(
            client,
            "part",
            "id",
            missing_part_ids,
            select_columns=(
                "id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag"
            ),
        )
        part_cost_map: dict[int, float] = {}
        if missing_part_ids:
            part_cost_map = self._load_part_cost_map(client, missing_part_ids)
        part_price_map: dict[int, float] = {}
        for row in product_rows:
            part_id = row.get("partId")
            if part_id is None:
                continue
            price = row.get("price")
            if price is None:
                continue
            price_value = float(price)
            if price_value == 0:
                continue
            part_price_map[int(part_id)] = price_value
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        if part_rows:
            self._upsert_part_rows(
                part_rows,
                part_type_map,
                unit_map,
                part_cost_map,
                part_price_map,
                template_model,
                product_maps["part"],
            )
            self._update_product_code_map_from_part_rows(part_rows, product_maps["part"], product_code_map)
        self._upsert_product_rows(
            product_rows,
            unit_map,
            part_price_map,
            template_model,
            product_maps["part"],
            product_maps["product"],
        )
        self._update_product_code_map_from_product_rows(product_rows, product_maps["product"], product_code_map)
        mapped_product_ids = {
            int(row["id"])
            for row in product_rows
            if int(row["id"]) in product_maps["product"]
        }
        if mapped_product_ids:
            _logger.info("Fishbowl import: hydrated %s missing products", len(mapped_product_ids))
        return mapped_product_ids

    def _import_missing_parts(
        self,
        client: FishbowlClient,
        missing_part_ids: set[int],
        part_type_map: dict[int, str],
        unit_map: dict[int, int],
        product_maps: dict[str, dict[int, int]],
        product_code_map: dict[str, int],
    ) -> set[int]:
        if not missing_part_ids:
            return set()
        part_rows = self._fetch_rows_by_ids(
            client,
            "part",
            "id",
            list(missing_part_ids),
            select_columns="id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag",
        )
        if not part_rows:
            return set()
        part_cost_map: dict[int, float] = {}
        if missing_part_ids:
            part_cost_map = self._load_part_cost_map(client, list(missing_part_ids))
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        self._upsert_part_rows(
            part_rows,
            part_type_map,
            unit_map,
            part_cost_map,
            {},
            template_model,
            product_maps["part"],
        )
        self._update_product_code_map_from_part_rows(part_rows, product_maps["part"], product_code_map)
        mapped_part_ids = {
            int(row["id"])
            for row in part_rows
            if int(row["id"]) in product_maps["part"]
        }
        if mapped_part_ids:
            _logger.info("Fishbowl import: hydrated %s missing parts", len(mapped_part_ids))
        return mapped_part_ids

    def _update_product_code_map_from_part_rows(
        self,
        part_rows: list[dict[str, Any]],
        part_product_map: dict[int, int],
        product_code_map: dict[str, int],
    ) -> None:
        for row in part_rows:
            default_code = str(row.get("num") or "").strip()
            if not default_code:
                continue
            part_id = int(row["id"])
            variant_id = part_product_map.get(part_id)
            if not variant_id:
                continue
            product_code_map[default_code] = variant_id

    def _update_product_code_map_from_product_rows(
        self,
        product_rows: list[dict[str, Any]],
        product_product_map: dict[int, int],
        product_code_map: dict[str, int],
    ) -> None:
        for row in product_rows:
            default_code = str(row.get("num") or "").strip()
            if not default_code:
                continue
            product_id = int(row["id"])
            variant_id = product_product_map.get(product_id)
            if not variant_id:
                continue
            product_code_map[default_code] = variant_id

    def _load_part_cost_map(self, client: FishbowlClient, part_ids: list[int]) -> dict[int, float]:
        cost_map: dict[int, float] = {}
        cost_rows = client.fetch_all(
            "SELECT partId, avgCost FROM partcost WHERE avgCost IS NOT NULL AND avgCost != 0"
        )
        for row in cost_rows:
            part_id_value = row.get("partId") or row.get("PARTID")
            avg_cost_value = row.get("avgCost") or row.get("AVGCOST")
            if part_id_value is None or avg_cost_value in (None, 0):
                continue
            cost_map[int(part_id_value)] = float(avg_cost_value)

        missing_ids = [part_id for part_id in part_ids if part_id not in cost_map]
        if not missing_ids:
            return cost_map

        for batch in chunked(missing_ids, 500):
            placeholders = ", ".join(["%s"] * len(batch))
            query = (
                "SELECT h.partId, h.avgCost, h.dateCaptured "
                "FROM partcosthistory h "
                "JOIN ("
                "  SELECT partId, MAX(dateCaptured) AS max_date "
                "  FROM partcosthistory "
                "  WHERE avgCost IS NOT NULL AND avgCost != 0 AND partId IN ("
                f"{placeholders}"
                ") GROUP BY partId"
                ") latest "
                "ON latest.partId = h.partId AND latest.max_date = h.dateCaptured"
            )
            history_rows = client.fetch_all(query, list(batch))
            for row in history_rows:
                part_id_value = row.get("partId") or row.get("PARTID")
                avg_cost_value = row.get("avgCost") or row.get("AVGCOST")
                if part_id_value is None or avg_cost_value in (None, 0):
                    continue
                part_id = int(part_id_value)
                if part_id in cost_map:
                    continue
                cost_map[part_id] = float(avg_cost_value)

        return cost_map

    def _load_sales_price_map(self, client: FishbowlClient, product_rows: list[dict[str, Any]]) -> dict[int, float]:
        product_part_map: dict[int, int] = {}
        for row in product_rows:
            product_id_value = row.get("id")
            part_id_value = row.get("partId")
            if product_id_value is None or part_id_value is None:
                continue
            product_part_map[int(product_id_value)] = int(part_id_value)

        latest_price_map: dict[int, tuple[datetime, int, float]] = {}
        last_id = 0
        while True:
            query = (
                "SELECT si.id, si.productId, si.unitPrice, so.dateIssued, so.dateCreated "
                "FROM soitem si JOIN so ON so.id = si.soId "
                "WHERE si.unitPrice IS NOT NULL AND si.unitPrice != 0 AND si.id > %s "
                "ORDER BY si.id LIMIT %s"
            )
            rows = client.fetch_all(query, [last_id, 20000])
            if not rows:
                break
            for row in rows:
                product_id_value = row.get("productId")
                if product_id_value is None:
                    continue
                part_id = product_part_map.get(int(product_id_value))
                if not part_id:
                    continue
                unit_price_value = row.get("unitPrice")
                if unit_price_value is None:
                    continue
                unit_price = float(unit_price_value)
                if unit_price == 0:
                    continue
                date_value = row.get("dateIssued") or row.get("dateCreated")
                date_key = date_value if date_value is not None else datetime.min
                row_id = int(row.get("id") or 0)
                existing = latest_price_map.get(part_id)
                if not existing or date_key > existing[0] or (date_key == existing[0] and row_id > existing[1]):
                    latest_price_map[part_id] = (date_key, row_id, unit_price)
            last_row_id = rows[-1].get("id") or rows[-1].get("ID")
            last_id = int(last_row_id or last_id)

        return {part_id: price for part_id, (_, __, price) in latest_price_map.items()}

    def _import_orders(
        self,
        client: FishbowlClient,
        partner_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> dict[str, dict[int, int]]:
        sales_status_map = self._load_status_map(client, "sostatus")
        purchase_status_map = self._load_status_map(client, "postatus")

        fishbowl_system = self._get_fishbowl_system()
        product_code_map = self._load_product_code_map()
        part_type_map = self._load_part_type_map(client)

        sales_order_rows = self._fetch_orders(
            client,
            "so",
            "dateIssued",
            start_datetime,
        )
        sales_line_batches = self._stream_order_lines(
            client,
            "soitem",
            "so",
            "soId",
            "dateIssued",
            start_datetime,
            select_columns="l.id, l.soId, l.productId, l.productNum, l.description, l.qtyOrdered, l.unitPrice, l.uomId",
        )
        sales_line_total = self._count_order_lines(client, "soitem", "so", "soId", "dateIssued", start_datetime)
        purchase_order_rows = self._fetch_orders(
            client,
            "po",
            "dateIssued",
            start_datetime,
        )
        purchase_line_batches = self._stream_order_lines(
            client,
            "poitem",
            "po",
            "poId",
            "dateIssued",
            start_datetime,
            select_columns="l.id, l.poId, l.partId, l.partNum, l.description, l.qtyToFulfill, l.unitCost, l.uomId",
        )
        purchase_line_total = self._count_order_lines(client, "poitem", "po", "poId", "dateIssued", start_datetime)

        unit_map = self._load_unit_map()
        sale_order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        sale_line_model = self.env["sale.order.line"].sudo().with_context(IMPORT_CONTEXT)
        purchase_order_model = self.env["purchase.order"].sudo().with_context(IMPORT_CONTEXT)
        purchase_line_model = self.env["purchase.order.line"].sudo().with_context(IMPORT_CONTEXT)

        sales_order_map: dict[int, int] = {}
        sales_line_map: dict[int, int] = {}
        purchase_order_map: dict[int, int] = {}
        purchase_line_map: dict[int, int] = {}
        unresolved_sales_product_ids: set[int] = set()
        unresolved_purchase_part_ids: set[int] = set()

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

        missing_sales_count = 0
        missing_sales_samples: list[str] = []
        missing_sales_buckets: dict[str, int] = {}
        sales_line_processed = 0
        sales_line_log_every = 25000
        sales_line_log_threshold = sales_line_log_every
        sales_line_started_at = time.monotonic()
        use_full_prefetch = start_datetime is None
        sales_existing_map: dict[str, int] = {}
        sales_stale_map: dict[str, models.Model] = {}
        sales_blocked: set[str] = set()
        if use_full_prefetch:
            sales_existing_map, sales_stale_map, sales_blocked = self._prefetch_external_id_records_full(
                fishbowl_system.id,
                RESOURCE_SALES_ORDER_LINE,
                "sale.order.line",
            )

        for sales_line_rows in sales_line_batches:
            external_ids = [str(int(row["id"])) for row in sales_line_rows]
            if not use_full_prefetch:
                sales_existing_map, sales_stale_map, sales_blocked = self._prefetch_external_id_records(
                    fishbowl_system.id,
                    RESOURCE_SALES_ORDER_LINE,
                    external_ids,
                    "sale.order.line",
                )
            candidate_product_ids = {
                int(row.get("productId"))
                for row in sales_line_rows
                if row.get("productId") is not None
            }
            missing_product_ids = {
                product_id
                for product_id in candidate_product_ids
                if product_id not in product_maps["product"] and product_id not in unresolved_sales_product_ids
            }
            if missing_product_ids:
                mapped_product_ids = self._import_missing_products(
                    client,
                    missing_product_ids,
                    part_type_map,
                    unit_map,
                    product_maps,
                    product_code_map,
                )
                unresolved_sales_product_ids.update(missing_product_ids - mapped_product_ids)
            create_values: list[dict[str, Any]] = []
            create_external_ids: list[str] = []

            for row in sales_line_rows:
                fishbowl_id = int(row["id"])
                external_id_value = str(fishbowl_id)
                if external_id_value in sales_blocked:
                    continue
                order_id = sales_order_map.get(int(row["soId"]))
                if not order_id:
                    continue
                product_id = self._resolve_product_from_sales_row(row, product_maps, product_code_map)
                missing_product = False
                bucket = ""
                if not product_id:
                    missing_product = True
                    bucket = self._legacy_bucket_for_line(
                        str(row.get("description") or ""),
                        float(row.get("unitPrice") or 0),
                    )
                    product_id = self._get_legacy_bucket_product_id(bucket)
                    missing_sales_count += 1
                    missing_sales_buckets[bucket] = missing_sales_buckets.get(bucket, 0) + 1
                    if len(missing_sales_samples) < 20:
                        missing_sales_samples.append(str(row.get("id")))
                unit_id = unit_map.get(int(row.get("uomId") or 0))
                quantity_ordered = row.get("qtyOrdered") or 0
                unit_price = row.get("unitPrice") or 0
                line_name = str(row.get("description") or "").strip() or False
                if missing_product:
                    line_name = self._build_legacy_line_name(
                        description=str(row.get("description") or ""),
                        reference=str(row.get("productNum") or ""),
                        fallback_product_id=product_id,
                    )
                values = {
                    "order_id": order_id,
                    "product_id": product_id or False,
                    "name": line_name or False,
                    "product_uom_qty": float(quantity_ordered),
                    "price_unit": float(unit_price),
                }
                if unit_id:
                    values["product_uom_id"] = unit_id
                existing_line_id = sales_existing_map.get(external_id_value)
                if existing_line_id:
                    sale_line_model.browse(existing_line_id).write(values)
                    sales_line_map[fishbowl_id] = existing_line_id
                    continue
                create_values.append(values)
                create_external_ids.append(external_id_value)

            if create_values:
                created_lines = sale_line_model.create(create_values)
                external_id_payloads: list[dict[str, Any]] = []
                for external_id_value, line in zip(create_external_ids, created_lines):
                    sales_line_map[int(external_id_value)] = line.id
                    sales_existing_map[external_id_value] = line.id
                    stale_record = sales_stale_map.pop(external_id_value, None)
                    if stale_record:
                        stale_record.write({"res_model": "sale.order.line", "res_id": line.id, "active": True})
                        continue
                    external_id_payloads.append(
                        {
                            "res_model": "sale.order.line",
                            "res_id": line.id,
                            "system_id": fishbowl_system.id,
                            "resource": RESOURCE_SALES_ORDER_LINE,
                            "external_id": external_id_value,
                            "active": True,
                        }
                    )
                if external_id_payloads:
                    self.env["external.id"].sudo().create(external_id_payloads)
            self._commit_and_clear()
            sales_line_processed += len(sales_line_rows)
            if sales_line_processed >= sales_line_log_threshold:
                elapsed = time.monotonic() - sales_line_started_at
                rate = sales_line_processed / elapsed if elapsed else 0.0
                if sales_line_total:
                    percent = (sales_line_processed / sales_line_total) * 100
                    remaining = max(sales_line_total - sales_line_processed, 0)
                    eta_minutes = (remaining / rate / 60) if rate else 0.0
                    _logger.info(
                        "Fishbowl import: sales lines %s/%s (%.1f%%) at %.0f rows/s, ETA %.1f min",
                        sales_line_processed,
                        sales_line_total,
                        percent,
                        rate,
                        eta_minutes,
                    )
                else:
                    _logger.info(
                        "Fishbowl import: sales lines processed %s in %.2fs",
                        sales_line_processed,
                        elapsed,
                    )
                sales_line_log_threshold += sales_line_log_every

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
                "note": row.get("note") or False,
                "state": order_state,
            }
            order = purchase_order_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PURCHASE_ORDER,
            )
            purchase_order_map[fishbowl_id] = order.id

        missing_purchase_count = 0
        missing_purchase_samples: list[str] = []
        missing_purchase_buckets: dict[str, int] = {}
        purchase_line_processed = 0
        purchase_line_log_every = 5000
        purchase_line_log_threshold = purchase_line_log_every
        purchase_line_started_at = time.monotonic()
        purchase_existing_map: dict[str, int] = {}
        purchase_stale_map: dict[str, models.Model] = {}
        purchase_blocked: set[str] = set()
        if use_full_prefetch:
            purchase_existing_map, purchase_stale_map, purchase_blocked = self._prefetch_external_id_records_full(
                fishbowl_system.id,
                RESOURCE_PURCHASE_ORDER_LINE,
                "purchase.order.line",
            )

        for purchase_line_rows in purchase_line_batches:
            external_ids = [str(int(row["id"])) for row in purchase_line_rows]
            if not use_full_prefetch:
                purchase_existing_map, purchase_stale_map, purchase_blocked = self._prefetch_external_id_records(
                    fishbowl_system.id,
                    RESOURCE_PURCHASE_ORDER_LINE,
                    external_ids,
                    "purchase.order.line",
                )
            candidate_part_ids = {
                int(row.get("partId"))
                for row in purchase_line_rows
                if row.get("partId") is not None
            }
            missing_part_ids = {
                part_id
                for part_id in candidate_part_ids
                if part_id not in product_maps["part"] and part_id not in unresolved_purchase_part_ids
            }
            if missing_part_ids:
                mapped_part_ids = self._import_missing_parts(
                    client,
                    missing_part_ids,
                    part_type_map,
                    unit_map,
                    product_maps,
                    product_code_map,
                )
                unresolved_purchase_part_ids.update(missing_part_ids - mapped_part_ids)
            create_values: list[dict[str, Any]] = []
            create_external_ids: list[str] = []

            for row in purchase_line_rows:
                fishbowl_id = int(row["id"])
                external_id_value = str(fishbowl_id)
                if external_id_value in purchase_blocked:
                    continue
                order_id = purchase_order_map.get(int(row["poId"]))
                if not order_id:
                    continue
                part_id = row.get("partId")
                product_id = product_maps["part"].get(int(part_id)) if part_id is not None else None
                missing_product = False
                bucket = ""
                if not product_id:
                    missing_product = True
                    bucket = self._legacy_bucket_for_line(
                        str(row.get("description") or ""),
                        float(row.get("unitCost") or 0),
                    )
                    product_id = self._get_legacy_bucket_product_id(bucket)
                    missing_purchase_count += 1
                    missing_purchase_buckets[bucket] = missing_purchase_buckets.get(bucket, 0) + 1
                    if len(missing_purchase_samples) < 20:
                        missing_purchase_samples.append(str(row.get("id")))
                unit_id = unit_map.get(int(row.get("uomId") or 0))
                quantity_ordered = row.get("qtyToFulfill") or 0
                unit_cost = row.get("unitCost") or 0
                line_name = str(row.get("description") or "").strip() or False
                if missing_product:
                    line_name = self._build_legacy_line_name(
                        description=str(row.get("description") or ""),
                        reference=str(row.get("partNum") or ""),
                        fallback_product_id=product_id,
                    )
                values = {
                    "order_id": order_id,
                    "product_id": product_id or False,
                    "name": line_name or False,
                    "product_qty": float(quantity_ordered),
                    "price_unit": float(unit_cost),
                }
                if unit_id:
                    values["product_uom_id"] = unit_id
                existing_line_id = purchase_existing_map.get(external_id_value)
                if existing_line_id:
                    purchase_line_model.browse(existing_line_id).write(values)
                    purchase_line_map[fishbowl_id] = existing_line_id
                    continue
                create_values.append(values)
                create_external_ids.append(external_id_value)

            if create_values:
                created_lines = purchase_line_model.create(create_values)
                external_id_payloads: list[dict[str, Any]] = []
                for external_id_value, line in zip(create_external_ids, created_lines):
                    purchase_line_map[int(external_id_value)] = line.id
                    purchase_existing_map[external_id_value] = line.id
                    stale_record = purchase_stale_map.pop(external_id_value, None)
                    if stale_record:
                        stale_record.write({"res_model": "purchase.order.line", "res_id": line.id, "active": True})
                        continue
                    external_id_payloads.append(
                        {
                            "res_model": "purchase.order.line",
                            "res_id": line.id,
                            "system_id": fishbowl_system.id,
                            "resource": RESOURCE_PURCHASE_ORDER_LINE,
                            "external_id": external_id_value,
                            "active": True,
                        }
                    )
                if external_id_payloads:
                    self.env["external.id"].sudo().create(external_id_payloads)
            self._commit_and_clear()
            purchase_line_processed += len(purchase_line_rows)
            if purchase_line_processed >= purchase_line_log_threshold:
                elapsed = time.monotonic() - purchase_line_started_at
                rate = purchase_line_processed / elapsed if elapsed else 0.0
                if purchase_line_total:
                    percent = (purchase_line_processed / purchase_line_total) * 100
                    remaining = max(purchase_line_total - purchase_line_processed, 0)
                    eta_minutes = (remaining / rate / 60) if rate else 0.0
                    _logger.info(
                        "Fishbowl import: purchase lines %s/%s (%.1f%%) at %.0f rows/s, ETA %.1f min",
                        purchase_line_processed,
                        purchase_line_total,
                        percent,
                        rate,
                        eta_minutes,
                    )
                else:
                    _logger.info(
                        "Fishbowl import: purchase lines processed %s in %.2fs",
                        purchase_line_processed,
                        elapsed,
                    )
                purchase_line_log_threshold += purchase_line_log_every

        if missing_sales_count:
            _logger.warning(
                "Missing product for %s Fishbowl sales lines; buckets=%s; sample_ids=%s",
                missing_sales_count,
                missing_sales_buckets,
                ", ".join(missing_sales_samples),
            )
        if missing_purchase_count:
            _logger.warning(
                "Missing product for %s Fishbowl purchase lines; buckets=%s; sample_ids=%s",
                missing_purchase_count,
                missing_purchase_buckets,
                ", ".join(missing_purchase_samples),
            )

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

        shipped_rows: list[dict[str, Any]] = []
        for row in shipment_rows:
            status_name = shipment_status_map.get(int(row.get("statusId") or 0), "")
            if status_name.lower() != "shipped":
                continue
            shipped_rows.append(row)

        shipment_external_ids = [str(int(row["id"])) for row in shipped_rows]
        shipment_existing_map, shipment_stale_map, shipment_blocked = self._prefetch_external_id_records(
            fishbowl_system.id,
            RESOURCE_SHIPMENT,
            shipment_external_ids,
            "stock.picking",
        )

        for row in shipped_rows:
            fishbowl_id = int(row["id"])
            external_id_value = str(fishbowl_id)
            if external_id_value in shipment_blocked:
                continue
            sale_order_id = order_maps["sales_order"].get(int(row.get("soId") or 0))
            partner_id = False
            if sale_order_id:
                partner_id = self.env["sale.order"].sudo().browse(sale_order_id).partner_id.id
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
                update_values = values.copy()
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
        )
        missing_sales_line_ids = {
            int(row["soItemId"])
            for row in shipment_item_rows
            if row.get("soItemId") is not None and int(row["soItemId"]) not in order_maps["sales_line"]
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
        for start_index in range(0, len(shipment_item_rows), shipment_line_batch_size):
            batch_rows = shipment_item_rows[start_index : start_index + shipment_line_batch_size]
            external_ids = [str(int(row["id"])) for row in batch_rows]
            existing_map, stale_map, blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_SHIPMENT_LINE,
                external_ids,
                "stock.move",
            )
            create_values: list[dict[str, Any]] = []
            create_external_ids: list[str] = []
            move_line_payloads: dict[str, dict[str, Any]] = {}
            batch_move_ids: dict[str, int] = {}

            for row in batch_rows:
                ship_id = row.get("shipId")
                if ship_id is None:
                    continue
                picking_id = shipment_map.get(int(ship_id))
                if not picking_id:
                    continue
                fishbowl_id = int(row["id"])
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
                unit_id = unit_map.get(int(row.get("uomId") or 0))
                quantity_shipped = row.get("qtyShipped") or 0
                move_values = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_shipped),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "sale_line_id": sale_line_id or False,
                }
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

            if create_values:
                created_moves = move_model.create(create_values)
                external_id_payloads: list[dict[str, Any]] = []
                for external_id_value, move in zip(create_external_ids, created_moves):
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
        done_picking_ids: dict[int, int] = {}
        receipt_line_processed = 0
        receipt_line_log_every = 5000
        receipt_line_log_threshold = receipt_line_log_every
        receipt_line_started_at = time.monotonic()
        receipt_line_batch_size = 2000
        fishbowl_system = self._get_fishbowl_system()
        receipt_ids = {
            int(row.get("receiptId"))
            for row in receipt_item_rows
            if row.get("receiptId") is not None
        }
        receipt_existing_map: dict[str, int] = {}
        receipt_stale_map: dict[str, models.Model] = {}
        receipt_blocked: set[str] = set()
        if receipt_ids:
            receipt_external_ids = [str(value) for value in receipt_ids]
            receipt_existing_map, receipt_stale_map, receipt_blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_RECEIPT,
                receipt_external_ids,
                "stock.picking",
            )

        for start_index in range(0, len(receipt_item_rows), receipt_line_batch_size):
            batch_rows = receipt_item_rows[start_index : start_index + receipt_line_batch_size]
            external_ids = [str(int(row["id"])) for row in batch_rows]
            existing_map, stale_map, blocked = self._prefetch_external_id_records(
                fishbowl_system.id,
                RESOURCE_RECEIPT_LINE,
                external_ids,
                "stock.move",
            )
            create_values: list[dict[str, Any]] = []
            create_external_ids: list[str] = []
            move_line_payloads: dict[str, dict[str, Any]] = {}
            batch_move_ids: dict[str, int] = {}

            for row in batch_rows:
                receipt_id = row.get("receiptId")
                if receipt_id is None:
                    continue
                fishbowl_receipt_id = int(receipt_id)
                receipt_external_id_value = str(fishbowl_receipt_id)
                if receipt_external_id_value in receipt_blocked:
                    continue
                picking_id = done_picking_ids.get(fishbowl_receipt_id)
                if not picking_id:
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
                        update_values = values.copy()
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

                fishbowl_line_id = int(row["id"])
                external_id_value = str(fishbowl_line_id)
                if external_id_value in blocked:
                    continue
                product_id = self._resolve_product_from_receipt_row(row, order_maps, product_maps)
                if not product_id:
                    continue
                product = self.env["product.product"].sudo().browse(product_id)
                if not self._is_stockable_product(product):
                    continue
                unit_id = unit_map.get(int(row.get("uomId") or 0))
                quantity_received = row.get("qty") or 0
                picking = picking_model.browse(picking_id)
                move_values = {
                    "product_id": product_id,
                    "product_uom_qty": float(quantity_received),
                    "product_uom": unit_id or product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                    "purchase_line_id": order_maps["purchase_line"].get(int(row.get("poItemId") or 0)) or False,
                }
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

            if create_values:
                created_moves = move_model.create(create_values)
                external_id_payloads: list[dict[str, Any]] = []
                for external_id_value, move in zip(create_external_ids, created_moves):
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

    def _import_on_hand(self, client: FishbowlClient, product_maps: dict[str, dict[int, int]]) -> None:
        stock_location = self._get_location("internal")
        quant_model = self.env["stock.quant"].sudo().with_context(IMPORT_CONTEXT, active_test=False)
        product_model = self.env["product.product"].sudo().with_context(IMPORT_CONTEXT, active_test=False)
        inventory_rows = client.fetch_all(
            "SELECT partId, SUM(qtyOnHand) AS qtyOnHand FROM qtyinventorytotals GROUP BY partId"
        )
        if not inventory_rows:
            _logger.warning("Fishbowl on-hand returned no rows; skipping on-hand sync.")
            return
        fishbowl_part_ids: set[int] = set()
        for row in inventory_rows:
            part_id_value = row.get("partId") or row.get("PARTID")
            if part_id_value is None:
                continue
            fishbowl_part_ids.add(int(part_id_value))
            product_id = product_maps["part"].get(int(part_id_value))
            if not product_id:
                continue
            product = product_model.browse(product_id)
            if not self._is_stockable_product(product):
                continue
            qty_value = row.get("qtyOnHand") or row.get("QTYONHAND") or 0
            target_quantity = float(qty_value)
            current_quantity = product.with_context(active_test=False, location=stock_location.id).qty_available
            delta_quantity = target_quantity - current_quantity
            if float_is_zero(delta_quantity, precision_rounding=product.uom_id.rounding):
                continue
            quant_model._update_available_quantity(product, stock_location, delta_quantity)

        # Clear any lingering on-hand quantities for parts no longer reported by Fishbowl.
        missing_part_ids = set(product_maps["part"]) - fishbowl_part_ids
        if missing_part_ids:
            missing_product_ids = [
                product_maps["part"][part_id]
                for part_id in missing_part_ids
                if part_id in product_maps["part"]
            ]
            cleared_count = 0
            for batch in chunked(missing_product_ids, 1000):
                group_rows = quant_model._read_group(
                    [
                        ("product_id", "in", batch),
                        ("location_id", "=", stock_location.id),
                        ("quantity", "!=", 0),
                    ],
                    ["product_id"],
                    ["quantity:sum"],
                )
                if not group_rows:
                    continue
                for product, group_quantity in group_rows:
                    if not product or not self._is_stockable_product(product):
                        continue
                    if float_is_zero(group_quantity, precision_rounding=product.uom_id.rounding):
                        continue
                    quant_model._update_available_quantity(product, stock_location, -float(group_quantity))
                    cleared_count += 1
            if cleared_count:
                _logger.info("Fishbowl import: cleared on-hand for %s stale products", cleared_count)
        self._commit_and_clear()

    def _commit_and_clear(self) -> None:
        self.env.cr.execute("SET LOCAL synchronous_commit TO OFF")
        self.env.cr.commit()
        self.env.clear()

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
            "service": "service",
            "labor": "service",
            "overhead": "service",
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
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw_value = bytes(value)
            if not raw_value:
                return False
            if all(byte in (0, 1) for byte in raw_value):
                return any(byte == 1 for byte in raw_value)
            try:
                decoded = raw_value.decode().strip()
            except Exception:
                return any(raw_value)
            return self._to_bool(decoded)
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

    def _load_product_code_map(self) -> dict[str, int]:
        product_rows = (
            self.env["product.product"]
            .sudo()
            .with_context(active_test=False)
            .search_read(
                [("default_code", "!=", False)],
                ["id", "default_code"],
            )
        )
        product_map: dict[str, int] = {}
        for row in product_rows:
            default_code = str(row.get("default_code") or "").strip()
            if not default_code:
                continue
            product_map[default_code] = int(row["id"])
        return product_map

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

    def _stream_order_lines(
        self,
        client: FishbowlClient,
        line_table: str,
        order_table: str,
        order_foreign_key: str,
        order_date_column: str,
        start_datetime: datetime | None,
        *,
        select_columns: str,
        batch_size: int = 20000,
    ) -> Iterator[list[dict[str, Any]]]:
        last_id = 0
        while True:
            conditions: list[str] = ["l.id > %s"]
            params: list[Any] = [last_id]
            if start_datetime is not None:
                conditions.append(f"o.{order_date_column} >= %s")
                params.append(start_datetime)
            where_clause = f" WHERE {' AND '.join(conditions)}"
            query = (
                f"SELECT {select_columns} FROM {line_table} l "
                f"JOIN {order_table} o ON o.id = l.{order_foreign_key}"
                f"{where_clause} ORDER BY l.id LIMIT %s"
            )
            params.append(batch_size)
            rows = client.fetch_all(query, params)
            if not rows:
                break
            yield rows
            last_row_id = rows[-1].get("id") or rows[-1].get("ID")
            last_id = int(last_row_id or last_id)

    def _count_order_lines(
        self,
        client: FishbowlClient,
        line_table: str,
        order_table: str,
        order_foreign_key: str,
        order_date_column: str,
        start_datetime: datetime | None,
    ) -> int:
        conditions: list[str] = []
        params: list[Any] = []
        if start_datetime is not None:
            conditions.append(f"o.{order_date_column} >= %s")
            params.append(start_datetime)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"SELECT COUNT(*) AS total FROM {line_table} l "
            f"JOIN {order_table} o ON o.id = l.{order_foreign_key}"
            f"{where_clause}"
        )
        result = client.fetch_all(query, params)
        if not result:
            return 0
        total_value = result[0].get("total") or result[0].get("TOTAL") or 0
        return int(total_value or 0)

    def _prefetch_external_id_records(
        self,
        system_id: int,
        resource: str,
        external_ids: list[str],
        expected_model: str,
    ) -> tuple[dict[str, int], dict[str, models.Model], set[str]]:
        if not external_ids:
            return {}, {}, set()
        external_id_model = self.env["external.id"].sudo()
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("external_id", "in", external_ids),
            ]
        )
        existing_map: dict[str, int] = {}
        stale_map: dict[str, models.Model] = {}
        blocked_ids: set[str] = set()
        expected_model_env = self.env[expected_model].sudo()
        for record in records:
            if record.res_model and record.res_model != expected_model:
                blocked_ids.add(record.external_id)
                continue
            if record.res_id:
                existing = expected_model_env.browse(record.res_id).exists()
                if existing:
                    existing_map[record.external_id] = existing.id
                    continue
            stale_map[record.external_id] = record
        return existing_map, stale_map, blocked_ids

    def _prefetch_external_id_records_full(
        self,
        system_id: int,
        resource: str,
        expected_model: str,
    ) -> tuple[dict[str, int], dict[str, models.Model], set[str]]:
        external_id_model = self.env["external.id"].sudo()
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
            ]
        )
        existing_map: dict[str, int] = {}
        stale_map: dict[str, models.Model] = {}
        blocked_ids: set[str] = set()
        expected_model_env = self.env[expected_model].sudo()
        for record in records:
            if record.res_model and record.res_model != expected_model:
                blocked_ids.add(record.external_id)
                continue
            if record.res_id:
                existing = expected_model_env.browse(record.res_id).exists()
                if existing:
                    existing_map[record.external_id] = existing.id
                    continue
            stale_map[record.external_id] = record
        return existing_map, stale_map, blocked_ids

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

    def _resolve_product_from_sales_row(
        self,
        row: dict[str, Any],
        product_maps: dict[str, dict[int, int]],
        product_code_map: dict[str, int] | None = None,
    ) -> int | None:
        product_id = row.get("productId")
        if product_id is not None and int(product_id) in product_maps["product"]:
            return product_maps["product"][int(product_id)]
        product_number = str(row.get("productNum") or "").strip()
        if product_number:
            if product_code_map is not None:
                cached_id = product_code_map.get(product_number)
                if cached_id:
                    return cached_id
            product = (
                self.env["product.product"]
                .sudo()
                .with_context(active_test=False)
                .search([("default_code", "=", product_number)], limit=1)
            )
            if product:
                return product.id
        return None

    def _legacy_bucket_for_line(self, description: str, unit_price: float) -> str:
        text = description.strip().lower()
        if unit_price < 0:
            return LEGACY_BUCKET_DISCOUNT
        if any(keyword in text for keyword in ("ship", "freight", "ups", "fedex", "dhl", "usps")):
            return LEGACY_BUCKET_SHIPPING
        if any(keyword in text for keyword in ("fee", "handling", "service charge", "credit card", "cc fee")):
            return LEGACY_BUCKET_FEE
        if any(keyword in text for keyword in ("discount", "coupon", "promo", "rebate", "markdown")):
            return LEGACY_BUCKET_DISCOUNT
        if any(keyword in text for keyword in ("misc", "other", "adjustment")):
            return LEGACY_BUCKET_MISC
        return LEGACY_BUCKET_ADHOC

    def _get_legacy_category(self) -> models.Model:
        category_model = self.env["product.category"].sudo().with_context(IMPORT_CONTEXT)
        category = category_model.search([("name", "=", "Legacy Fishbowl")], limit=1)
        return category or category_model.create({"name": "Legacy Fishbowl"})

    def _get_legacy_bucket_product_id(self, bucket: str) -> int:
        bucket_map = {
            LEGACY_BUCKET_SHIPPING: ("LEGACY-SHIPPING", "Legacy Shipping"),
            LEGACY_BUCKET_FEE: ("LEGACY-FEE", "Legacy Fee"),
            LEGACY_BUCKET_DISCOUNT: ("LEGACY-DISCOUNT", "Legacy Discount"),
            LEGACY_BUCKET_MISC: ("LEGACY-MISC", "Legacy Misc Charge"),
            LEGACY_BUCKET_ADHOC: ("LEGACY-ADHOC", "Legacy Ad-hoc Item"),
        }
        code, name = bucket_map.get(bucket, bucket_map[LEGACY_BUCKET_ADHOC])
        product_model = self.env["product.product"].sudo().with_context(IMPORT_CONTEXT)
        product = product_model.search([("default_code", "=", code)], limit=1)
        if product:
            return product.id
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        values = {
            "name": name,
            "default_code": code,
            "categ_id": self._get_legacy_category().id,
            "sale_ok": False,
            "purchase_ok": False,
            "active": True,
        }
        values[self._product_type_field(template_model)] = "service"
        template = template_model.create(values)
        return template.product_variant_id.id

    def _build_legacy_line_name(self, description: str, reference: str, fallback_product_id: int | None) -> str:
        description_value = description.strip()
        reference_value = reference.strip()
        if reference_value and reference_value not in description_value:
            line_name = f"{reference_value} - {description_value}" if description_value else reference_value
        else:
            line_name = description_value
        if not line_name and fallback_product_id:
            product = self.env["product.product"].sudo().browse(fallback_product_id)
            line_name = product.display_name
        return line_name

    def _is_stockable_product(self, product: models.Model) -> bool:
        if "is_storable" in product._fields:
            return bool(product.is_storable)
        type_field = "detailed_type" if "detailed_type" in product._fields else "type"
        return getattr(product, type_field, "") == "product"

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
