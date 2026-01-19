import logging
from datetime import datetime

from odoo import models

from ..services.fishbowl_client import FishbowlClient, chunked
from . import fishbowl_rows
from .fishbowl_import_constants import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_PART, RESOURCE_PRODUCT

_logger = logging.getLogger(__name__)


# External Fishbowl schema; SQL resolver has no catalog.
# noinspection SqlResolve
class FishbowlImporterProducts(models.Model):
    _inherit = "fishbowl.importer"

    def _import_products(self, client: FishbowlClient) -> dict[str, dict[int, int]]:
        part_type_map = self._load_part_type_map(client)
        part_rows = self._fetch_rows(
            client,
            fishbowl_rows.PART_ROWS_ADAPTER,
            "SELECT id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag "
            "FROM part ORDER BY id",
        )
        product_rows = self._fetch_rows(
            client,
            fishbowl_rows.PRODUCT_ROWS_ADAPTER,
            "SELECT id, partId, num, description, price, uomId, activeFlag FROM product ORDER BY id",
        )

        part_ids = [row.id for row in part_rows]
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

    @staticmethod
    def _load_part_type_map(client: FishbowlClient) -> dict[int, str]:
        part_type_rows = fishbowl_rows.PART_TYPE_ROWS_ADAPTER.validate_python(
            client.fetch_all("SELECT id, name FROM parttype ORDER BY id")
        )
        return {row.id: str(row.name or "").strip().lower() for row in part_type_rows}

    def _upsert_part_rows(
        self,
        part_rows: list[fishbowl_rows.PartRow],
        part_type_map: dict[int, str],
        unit_map: dict[int, int],
        part_cost_map: dict[int, float],
        part_price_map: dict[int, float],
        template_model: "odoo.model.product_template",
        part_product_map: dict[int, int],
    ) -> None:
        for row in part_rows:
            fishbowl_id = row.id
            unit_id = unit_map.get(row.uomId or 0)
            part_type_name = part_type_map.get(row.typeId or 0, "")
            product_type = self._map_part_type(part_type_name)
            values: "odoo.values.product_template" = {
                "name": str(row.description or row.num or "").strip() or f"Part {fishbowl_id}",
                "default_code": str(row.num or "").strip() or False,
                "description": row.details or False,
                "active": True,
                "sale_ok": True,
                "purchase_ok": product_type in {"product", "consu"},
                "tracking": self._map_tracking(row.trackingFlag, row.serializedFlag),
            }
            if unit_id:
                values["uom_id"] = unit_id
            values[self._product_type_field(template_model)] = product_type
            if "is_storable" in template_model._fields:
                values["is_storable"] = product_type != "service"
            standard_price = part_cost_map.get(fishbowl_id)
            if standard_price is None:
                standard_price = row.stdCost
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
        product_rows: list[fishbowl_rows.ProductRow],
        unit_map: dict[int, int],
        part_price_map: dict[int, float],
        template_model: "odoo.model.product_template",
        part_product_map: dict[int, int],
        product_product_map: dict[int, int],
    ) -> None:
        for row in product_rows:
            fishbowl_id = row.id
            part_id = row.partId
            if part_id is None:
                continue
            variant_id = part_product_map.get(part_id)
            if not variant_id:
                continue
            variant = self.env["product.product"].browse(variant_id)
            template = template_model.browse(variant.product_tmpl_id.id)
            values: "odoo.values.product_template" = {
                "name": str(row.description or row.num or template.name).strip(),
                "active": True,
                "sale_ok": True,
            }
            if "is_storable" in template._fields:
                product_type_field = self._product_type_field(template)
                values["is_storable"] = getattr(template, product_type_field, "") != "service"
            list_price = row.price
            if list_price is None or float(list_price) == 0:
                fallback_price = part_price_map.get(part_id)
                if fallback_price is not None:
                    list_price = fallback_price
            if list_price is not None and float(list_price) != 0:
                values["list_price"] = float(list_price)
            unit_id = unit_map.get(row.uomId or 0)
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
        product_rows: list[fishbowl_rows.ProductRow] = self._fetch_rows_by_ids(
            client,
            "product",
            "id",
            list(missing_product_ids),
            select_columns="id, partId, num, description, price, uomId, activeFlag",
            row_parser=fishbowl_rows.PRODUCT_ROWS_ADAPTER.validate_python,
        )
        if not product_rows:
            return set()
        part_ids: list[int] = []
        for row in product_rows:
            part_id = row.partId
            if part_id is None:
                continue
            part_ids.append(part_id)
        missing_part_ids = [part_id for part_id in part_ids if part_id not in product_maps["part"]]
        part_rows: list[fishbowl_rows.PartRow] = self._fetch_rows_by_ids(
            client,
            "part",
            "id",
            missing_part_ids,
            select_columns="id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag",
            row_parser=fishbowl_rows.PART_ROWS_ADAPTER.validate_python,
        )
        part_cost_map: dict[int, float] = {}
        if missing_part_ids:
            part_cost_map = self._load_part_cost_map(client, missing_part_ids)
        part_price_map: dict[int, float] = {}
        for row in product_rows:
            part_id = row.partId
            if part_id is None:
                continue
            price = row.price
            if price is None:
                continue
            price_value = float(price)
            if price_value == 0:
                continue
            part_price_map[part_id] = price_value
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
        mapped_product_ids = {row.id for row in product_rows if row.id in product_maps["product"]}
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
        part_rows: list[fishbowl_rows.PartRow] = self._fetch_rows_by_ids(
            client,
            "part",
            "id",
            list(missing_part_ids),
            select_columns="id, num, description, details, uomId, typeId, trackingFlag, serializedFlag, stdCost, activeFlag",
            row_parser=fishbowl_rows.PART_ROWS_ADAPTER.validate_python,
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
        mapped_part_ids = {row.id for row in part_rows if row.id in product_maps["part"]}
        if mapped_part_ids:
            _logger.info("Fishbowl import: hydrated %s missing parts", len(mapped_part_ids))
        return mapped_part_ids

    @staticmethod
    def _update_product_code_map_from_part_rows(
        part_rows: list[fishbowl_rows.PartRow],
        part_product_map: dict[int, int],
        product_code_map: dict[str, int],
    ) -> None:
        for row in part_rows:
            default_code = str(row.num or "").strip()
            if not default_code:
                continue
            part_id = row.id
            variant_id = part_product_map.get(part_id)
            if not variant_id:
                continue
            product_code_map[default_code] = variant_id

    @staticmethod
    def _update_product_code_map_from_product_rows(
        product_rows: list[fishbowl_rows.ProductRow],
        product_product_map: dict[int, int],
        product_code_map: dict[str, int],
    ) -> None:
        for row in product_rows:
            default_code = str(row.num or "").strip()
            if not default_code:
                continue
            product_id = row.id
            variant_id = product_product_map.get(product_id)
            if not variant_id:
                continue
            product_code_map[default_code] = variant_id

    @staticmethod
    def _load_part_cost_map(client: FishbowlClient, part_ids: list[int]) -> dict[int, float]:
        cost_map: dict[int, float] = {}
        cost_rows = fishbowl_rows.PART_COST_ROWS_ADAPTER.validate_python(
            client.fetch_all("SELECT partId, avgCost FROM partcost WHERE avgCost IS NOT NULL AND avgCost != 0")
        )
        for row in cost_rows:
            if row.partId is None or row.avgCost in (None, 0):
                continue
            cost_map[row.partId] = float(row.avgCost)

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
            history_rows = fishbowl_rows.PART_COST_HISTORY_ROWS_ADAPTER.validate_python(history_rows)
            for row in history_rows:
                if row.partId is None or row.avgCost in (None, 0):
                    continue
                if row.partId in cost_map:
                    continue
                cost_map[row.partId] = float(row.avgCost)

        return cost_map

    @staticmethod
    def _load_sales_price_map(client: FishbowlClient, product_rows: list[fishbowl_rows.ProductRow]) -> dict[int, float]:
        product_part_map: dict[int, int] = {}
        for row in product_rows:
            if row.partId is None:
                continue
            product_part_map[row.id] = row.partId

        latest_price_map: dict[int, tuple[datetime, int, float]] = {}
        last_id = 0
        while True:
            query = (
                "SELECT si.id, si.productId, si.unitPrice, so.dateIssued, so.dateCreated "
                "FROM soitem si JOIN so ON so.id = si.soId "
                "WHERE si.unitPrice IS NOT NULL AND si.unitPrice != 0 AND si.id > %s "
                "ORDER BY si.id LIMIT %s"
            )
            rows = fishbowl_rows.SALES_PRICE_ROWS_ADAPTER.validate_python(client.fetch_all(query, [last_id, 20000]))
            if not rows:
                break
            for row in rows:
                if row.productId is None:
                    continue
                part_id = product_part_map.get(row.productId)
                if not part_id:
                    continue
                if row.unitPrice is None:
                    continue
                unit_price = float(row.unitPrice)
                if unit_price == 0:
                    continue
                date_value = row.dateIssued or row.dateCreated
                date_key = date_value if date_value is not None else datetime.min
                row_id = row.id
                existing = latest_price_map.get(part_id)
                if not existing or date_key > existing[0] or (date_key == existing[0] and row_id > existing[1]):
                    latest_price_map[part_id] = (date_key, row_id, unit_price)
            last_id = rows[-1].id

        return {part_id: price for part_id, (_, __, price) in latest_price_map.items()}

    @staticmethod
    def _map_part_type(part_type_name: str) -> str:
        mapping = {
            "service": "service",
            "labor": "service",
            "overhead": "service",
        }
        return mapping.get(part_type_name.lower(), "consu")

    def _map_tracking(self, tracking_flag: object, serialized_flag: object) -> str:
        if self._to_bool(serialized_flag):
            return "serial"
        if self._to_bool(tracking_flag):
            return "lot"
        return "none"
