import logging
import re
from datetime import datetime

from odoo import models
from repairshopr_api import models as repairshopr_models
from repairshopr_api.client import Client

from .repairshopr_importer import (
    DEFAULT_SERVICE_PRODUCT_CODE,
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    RESOURCE_PRODUCT,
)

_logger = logging.getLogger(__name__)


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_products(self, repairshopr_client: Client, start_datetime: datetime | None) -> None:
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
                product_record.write(values)
                continue
            matched_record = self._match_existing_product(product_model, product)
            if matched_record:
                merged_values = self._merge_values_for_existing_product(matched_record, values)
                if merged_values:
                    matched_record.write(merged_values)
                matched_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(product.id), RESOURCE_PRODUCT)
                continue
            product_record = product_model.create(values)
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
            barcode_matches = product_model.search([("barcode", "=", barcode_value)], limit=2)
            if len(barcode_matches) == 1:
                return barcode_matches
            if len(barcode_matches) > 1:
                _logger.warning(
                    "RepairShopr product barcode %s matched multiple products: %s",
                    barcode_value,
                    barcode_matches.ids,
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
        candidates = product_model.search([("name", "ilike", match_name)], limit=25)
        if not candidates:
            return product_model.browse()
        name_keys = self._build_name_keys(match_name, description_values)
        exact_name_matches = candidates.filtered(
            lambda record: self._normalize_text(record.name or "") in name_keys
        )
        if len(exact_name_matches) == 1:
            return exact_name_matches

        description_match = self._match_product_by_description(exact_name_matches or candidates, description_values)
        if description_match:
            return description_match

        category_match = self._match_product_by_category(exact_name_matches or candidates, category_names)
        if category_match:
            return category_match

        if len(exact_name_matches) == 0 and len(candidates) == 1:
            return candidates
        if len(exact_name_matches) > 1 or len(candidates) > 1:
            _logger.warning(
                "RepairShopr product name '%s' matched multiple products: %s",
                match_name,
                (exact_name_matches or candidates).ids,
            )
        return product_model.browse()

    def _match_product_by_description(
        self,
        candidates: "odoo.model.product_template",
        description_values: list[str],
    ) -> "odoo.model.product_template":
        if not candidates or not description_values:
            return candidates.browse()
        for description_value in description_values:
            normalized_description = self._normalize_text(description_value)
            if not normalized_description:
                continue
            description_matches = candidates.filtered(
                lambda record: self._normalize_text(record.description or record.description_sale or "")
                == normalized_description
            )
            if len(description_matches) == 1:
                return description_matches
        return candidates.browse()

    def _match_product_by_category(
        self,
        candidates: "odoo.model.product_template",
        category_names: list[str],
    ) -> "odoo.model.product_template":
        if not candidates or not category_names:
            return candidates.browse()
        normalized_categories = {
            self._normalize_text(category) for category in category_names if self._normalize_text(category)
        }
        if not normalized_categories:
            return candidates.browse()
        category_matches = candidates.filtered(
            lambda record: self._normalize_text(record.categ_id.name or "") in normalized_categories
        )
        if len(category_matches) == 1:
            return category_matches
        return candidates.browse()

    def _merge_values_for_existing_product(
        self,
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
