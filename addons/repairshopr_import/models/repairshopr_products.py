import logging
import re
from datetime import datetime

from odoo import models

from ..services import repairshopr_sync_models as repairshopr_models
from ..services.repairshopr_sync_client import RepairshoprSyncClient

from .repairshopr_importer import (
    DEFAULT_SERVICE_PRODUCT_CODE,
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    RESOURCE_PRODUCT,
)

_logger = logging.getLogger(__name__)


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_products(self, repairshopr_client: RepairshoprSyncClient, start_datetime: datetime | None) -> None:
        product_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        products = repairshopr_client.get_model(repairshopr_models.Product, updated_at=start_datetime)
        for product in products:
            product_record = product_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(product.id),
                RESOURCE_PRODUCT,
            )
            values = self._build_product_values(product)
            if product_record:
                safe_values = self._sanitize_update_values(product_record, values)
                safe_values, standard_price = self._extract_standard_price(safe_values)
                self._write_product_values(product_record, safe_values, standard_price)
                continue
            matched_record = self._match_existing_product(product_model, product)
            if matched_record:
                merged_values = self._merge_values_for_existing_product(matched_record, values)
                safe_values = self._sanitize_update_values(matched_record, merged_values)
                safe_values, standard_price = self._extract_standard_price(safe_values)
                self._write_product_values(matched_record, safe_values, standard_price)
                matched_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(product.id), RESOURCE_PRODUCT)
                continue
            safe_values = self._sanitize_create_values(values)
            safe_values, standard_price = self._extract_standard_price(safe_values)
            product_record = product_model.create(safe_values)
            if standard_price is not None:
                product_record.with_context(disable_auto_revaluation=True).write({"standard_price": standard_price})
            product_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(product.id), RESOURCE_PRODUCT)

    def _build_product_values(self, product: repairshopr_models.Product) -> "odoo.values.product_template":
        name = self._select_product_name(product)
        values: "odoo.values.product_template" = {
            "name": name,
            "list_price": float(product.price_retail or 0.0),
            "standard_price": float(product.price_cost or 0.0),
            "description": product.description or "",
            "description_sale": product.long_description or "",
            "active": not bool(product.disabled),
        }
        barcode_value = self._normalize_barcode(product.upc_code)
        if barcode_value:
            values["barcode"] = barcode_value
        return values

    @staticmethod
    def _select_product_name(product: repairshopr_models.Product) -> str:
        return product.name or product.description or f"RepairShopr Product {product.id}"

    @staticmethod
    def _select_product_match_name(product: repairshopr_models.Product) -> str | None:
        for value in (product.name, product.description, product.long_description):
            if value and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _select_description_values(product: repairshopr_models.Product) -> list[str]:
        descriptions: list[str] = []
        for value in (product.long_description, product.description):
            if value and value.strip():
                descriptions.append(value.strip())
        return descriptions

    @staticmethod
    def _select_category_names(product: repairshopr_models.Product) -> list[str]:
        categories: list[str] = []
        if product.product_category:
            categories.append(product.product_category)
        if product.category_path:
            parts = [part.strip() for part in product.category_path.split(">") if part.strip()]
            if parts:
                categories.append(parts[-1])
        return categories

    def _match_existing_product(
        self,
        product_model: "odoo.model.product_template",
        product: repairshopr_models.Product,
    ) -> "odoo.model.product_template":
        barcode_value = self._normalize_barcode(product.upc_code)
        if barcode_value:
            variant_model = self.env["product.product"].sudo().with_context(active_test=False)
            variant_matches = variant_model.search([("barcode", "=", barcode_value)], limit=2)
            if len(variant_matches) == 1:
                template_record = variant_matches.product_tmpl_id
                return product_model.browse(template_record.id)
            if len(variant_matches) > 1:
                _logger.warning(
                    "RepairShopr product barcode %s matched multiple variants: %s",
                    barcode_value,
                    variant_matches.ids,
                )
                return product_model.browse()

        match_name = self._select_product_match_name(product)
        if not match_name:
            return product_model.browse()
        category_names = self._select_category_names(product)
        description_values = self._select_description_values(product)
        return self._match_product_by_name(product_model, match_name, category_names, description_values)

    def _match_product_by_name(
        self,
        product_model: "odoo.model.product_template",
        match_name: str,
        category_names: list[str],
        description_values: list[str],
    ) -> "odoo.model.product_template":
        normalized_name = self._normalize_text(match_name)
        if not normalized_name:
            return product_model.browse()
        candidate_data = product_model.search_read(
            [("name", "ilike", match_name)],
            ["name", "description", "description_sale", "categ_id"],
            limit=25,
        )
        if not candidate_data:
            return product_model.browse()
        name_keys = self._build_name_keys(match_name, description_values)
        exact_name_ids: list[int] = []
        for row in candidate_data:
            record_id = self._coerce_record_id(row.get("id"))
            if record_id is None:
                continue
            if self._normalize_text(str(row.get("name") or "")) in name_keys:
                exact_name_ids.append(record_id)
        if len(exact_name_ids) == 1:
            return product_model.browse(exact_name_ids[0])

        description_match_id = self._match_candidate_by_description(candidate_data, description_values)
        if description_match_id:
            return product_model.browse(description_match_id)

        category_match_id = self._match_candidate_by_category(candidate_data, category_names)
        if category_match_id:
            return product_model.browse(category_match_id)

        candidate_ids = [record_id for row in candidate_data if (record_id := self._coerce_record_id(row.get("id"))) is not None]
        if not exact_name_ids and len(candidate_ids) == 1:
            return product_model.browse(candidate_ids[0])
        if len(exact_name_ids) > 1 or len(candidate_ids) > 1:
            _logger.warning(
                "RepairShopr product name '%s' matched multiple products: %s",
                match_name,
                exact_name_ids or candidate_ids,
            )
        return product_model.browse()

    def _match_candidate_by_description(
        self,
        candidate_data: list[dict[str, object]],
        description_values: list[str],
    ) -> int | None:
        if not candidate_data or not description_values:
            return None
        for description_value in description_values:
            normalized_description = self._normalize_text(description_value)
            if not normalized_description:
                continue
            matching_ids: list[int] = []
            for row in candidate_data:
                record_id = self._coerce_record_id(row.get("id"))
                if record_id is None:
                    continue
                normalized_candidate = self._normalize_text(str(row.get("description") or row.get("description_sale") or ""))
                if normalized_candidate == normalized_description:
                    matching_ids.append(record_id)
            if len(matching_ids) == 1:
                return matching_ids[0]
        return None

    def _match_candidate_by_category(
        self,
        candidate_data: list[dict[str, object]],
        category_names: list[str],
    ) -> int | None:
        if not candidate_data or not category_names:
            return None
        normalized_categories = {self._normalize_text(category) for category in category_names if self._normalize_text(category)}
        if not normalized_categories:
            return None
        matching_ids: list[int] = []
        for row in candidate_data:
            record_id = self._coerce_record_id(row.get("id"))
            if record_id is None:
                continue
            category_info = row.get("categ_id")
            if not category_info:
                continue
            category_name = category_info[1] if isinstance(category_info, (list, tuple)) and len(category_info) > 1 else ""
            if self._normalize_text(str(category_name)) in normalized_categories:
                matching_ids.append(record_id)
        if len(matching_ids) == 1:
            return matching_ids[0]
        return None

    @staticmethod
    def _merge_values_for_existing_product(
        product_record: "odoo.model.product_template",
        values: "odoo.values.product_template",
    ) -> "odoo.values.product_template":
        merged_values: "odoo.values.product_template" = {}
        for field_name in ("barcode", "description", "description_sale", "list_price", "standard_price"):
            incoming_value = values.get(field_name)
            if not incoming_value:
                continue
            existing_value = getattr(product_record, field_name, None)
            if existing_value:
                continue
            merged_values[field_name] = incoming_value
        if values.get("active") and not product_record.active:
            merged_values["active"] = True
        return merged_values

    def _sanitize_update_values(
        self,
        product_record: "odoo.model.product_template",
        values: "odoo.values.product_template",
    ) -> "odoo.values.product_template":
        if not values:
            return values
        sanitized_values: "odoo.values.product_template" = dict(values)
        barcode_value = sanitized_values.get("barcode")
        if not barcode_value:
            return sanitized_values
        existing_barcode = product_record.barcode or ""
        if existing_barcode and existing_barcode != barcode_value:
            sanitized_values.pop("barcode", None)
            _logger.warning(
                "RepairShopr product %s wants barcode %s but product %s already has %s; skipping barcode update.",
                product_record.display_name,
                barcode_value,
                product_record.id,
                existing_barcode,
            )
            return sanitized_values
        excluded_variant_ids = None
        if product_record.product_variant_id:
            excluded_variant_ids = [product_record.product_variant_id.id]
        duplicate = self._find_barcode_variant(barcode_value, excluded_variant_ids=excluded_variant_ids)
        if duplicate:
            sanitized_values.pop("barcode", None)
            _logger.warning(
                "RepairShopr barcode %s already assigned to product %s; skipping barcode update for %s.",
                barcode_value,
                duplicate.display_name,
                product_record.display_name,
            )
        return sanitized_values

    def _sanitize_create_values(
        self,
        values: "odoo.values.product_template",
    ) -> "odoo.values.product_template":
        if not values:
            return values
        sanitized_values: "odoo.values.product_template" = dict(values)
        barcode_value = sanitized_values.get("barcode")
        if not barcode_value:
            return sanitized_values
        duplicate = self._find_barcode_variant(barcode_value, excluded_variant_ids=None)
        if duplicate:
            sanitized_values.pop("barcode", None)
            _logger.warning(
                "RepairShopr barcode %s already assigned to product %s; skipping barcode on new product.",
                barcode_value,
                duplicate.display_name,
            )
        return sanitized_values

    def _find_barcode_variant(
        self,
        barcode_value: str,
        excluded_variant_ids: list[int] | None,
    ) -> "odoo.model.product_product":
        product_variant_model = self.env["product.product"].sudo().with_context(active_test=False)
        domain: list[tuple[str, str, object]] = [("barcode", "=", barcode_value)]
        if excluded_variant_ids:
            domain.append(("id", "not in", excluded_variant_ids))
        return product_variant_model.search(domain, limit=1)

    @staticmethod
    def _extract_standard_price(
        values: "odoo.values.product_template",
    ) -> tuple["odoo.values.product_template", float | None]:
        if not values:
            return values, None
        sanitized_values: "odoo.values.product_template" = dict(values)
        standard_price = sanitized_values.pop("standard_price", None)
        return sanitized_values, standard_price

    @staticmethod
    def _write_product_values(
        product_record: "odoo.model.product_template",
        values: "odoo.values.product_template",
        standard_price: float | None,
    ) -> None:
        if values:
            product_record.write(values)
        if standard_price is not None:
            product_record.with_context(disable_auto_revaluation=True).write({"standard_price": standard_price})

    @staticmethod
    def _normalize_barcode(value: str | None) -> str | None:
        if not value:
            return None
        return re.sub(r"[^0-9A-Za-z]+", "", value).strip() or None

    @staticmethod
    def _normalize_text(value: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z]+", " ", value or "").strip().lower()
        return re.sub(r"\s+", " ", cleaned)

    def _build_name_keys(self, match_name: str, description_values: list[str]) -> set[str]:
        name_keys = {self._normalize_text(match_name)}
        for description_value in description_values:
            for separator in (" ", " - "):
                combined = f"{match_name}{separator}{description_value}"
                normalized = self._normalize_text(combined)
                if normalized:
                    name_keys.add(normalized)
        return {name_key for name_key in name_keys if name_key}

    @staticmethod
    def _coerce_record_id(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _get_product_variant_for_line_item(
        self,
        product_id: int | None,
        fallback_name: str | None,
    ) -> "odoo.model.product_product":
        if product_id:
            template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
            product_template = template_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(product_id),
                RESOURCE_PRODUCT,
            )
            if product_template:
                return product_template.product_variant_id
        return self._get_fallback_service_product(fallback_name)

    def _get_fallback_service_product(self, fallback_name: str | None) -> "odoo.model.product_product":
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        product_template = template_model.search([("default_code", "=", DEFAULT_SERVICE_PRODUCT_CODE)], limit=1)
        if not product_template:
            values: dict[str, object] = {
                "name": fallback_name or "RepairShopr Service",
                "default_code": DEFAULT_SERVICE_PRODUCT_CODE,
                "list_price": 0.0,
                "standard_price": 0.0,
            }
            detailed_field_name = "detailed_type"
            if detailed_field_name in template_model._fields:
                values[detailed_field_name] = "service"
            elif "type" in template_model._fields:
                values["type"] = "service"
            product_template = template_model.create(values)
        return product_template.product_variant_id
