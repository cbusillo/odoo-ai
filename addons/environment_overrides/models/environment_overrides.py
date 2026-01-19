import logging
import os

from odoo import models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

CONFIG_PARAM_PREFIX = "ENV_OVERRIDE_CONFIG_PARAM__"
SHOPIFY_PREFIX = "ENV_OVERRIDE_SHOPIFY__"
AUTHENTIK_CONFIG_MODEL = "authentik.sso.config"
AUTHENTIK_GROUP_MAPPING_MODEL = "authentik.sso.group.mapping"

FALSE_VALUES = {"", "0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_PRODUCTION_INDICATORS = ("production", "live", "prod-")


def _normalize_config_param_value(raw_value: str) -> str:
    value = raw_value.strip()
    lowered = value.lower()
    if lowered in FALSE_VALUES:
        return "False"
    if lowered in TRUE_VALUES:
        return "True"
    return value


def _parse_boolean(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in FALSE_VALUES:
        return False
    if value in TRUE_VALUES:
        return True
    return default


class EnvironmentOverrides(models.AbstractModel):
    _name = "environment.overrides"
    _description = "Environment Overrides"

    def apply_from_env(self) -> None:
        self._apply_config_param_overrides()
        self._apply_authentik_overrides()
        self._apply_shopify_overrides()

    def _apply_authentik_overrides(self) -> None:
        authentik_config_model = self.env.get(AUTHENTIK_CONFIG_MODEL)
        if authentik_config_model is None:
            return

        apply_from_env = getattr(authentik_config_model.sudo(), "apply_from_env", None)
        if callable(apply_from_env):
            apply_from_env()

        group_mapping_model = self.env.get(AUTHENTIK_GROUP_MAPPING_MODEL)
        if group_mapping_model is None:
            return

        ensure_default_mappings = getattr(group_mapping_model.sudo(), "ensure_default_mappings", None)
        if callable(ensure_default_mappings):
            ensure_default_mappings()

    def _apply_config_param_overrides(self) -> None:
        overrides: dict[str, str] = {}
        prefix_length = len(CONFIG_PARAM_PREFIX)
        for raw_key, raw_value in os.environ.items():
            if not raw_key.startswith(CONFIG_PARAM_PREFIX):
                continue
            if len(raw_key) <= prefix_length:
                continue
            suffix = raw_key[prefix_length:]
            if not suffix:
                continue
            param_key = suffix.replace("__", ".").lower()
            overrides[param_key] = _normalize_config_param_value(raw_value)

        if not overrides:
            return

        parameter_model = self.env["ir.config_parameter"].sudo()
        _logger.info(
            "Applying %d environment config parameter overrides.",
            len(overrides),
        )
        for key, value in overrides.items():
            parameter_model.set_param(key, value)

    def _apply_shopify_overrides(self) -> None:
        shop_url_key = os.environ.get(f"{SHOPIFY_PREFIX}SHOP_URL_KEY", "").strip()
        api_token = os.environ.get(f"{SHOPIFY_PREFIX}API_TOKEN", "").strip()
        webhook_key = os.environ.get(f"{SHOPIFY_PREFIX}WEBHOOK_KEY", "").strip()
        api_version = os.environ.get(f"{SHOPIFY_PREFIX}API_VERSION", "").strip()
        test_store_raw = os.environ.get(f"{SHOPIFY_PREFIX}TEST_STORE")
        test_store = _parse_boolean(test_store_raw, default=True)

        indicators_raw = os.environ.get(f"{SHOPIFY_PREFIX}PRODUCTION_INDICATORS")
        if indicators_raw is None:
            production_indicators = list(DEFAULT_PRODUCTION_INDICATORS)
        else:
            cleaned = [item.strip().lower() for item in indicators_raw.split(",") if item.strip()]
            production_indicators = cleaned or list(DEFAULT_PRODUCTION_INDICATORS)

        required_values = [shop_url_key, api_token, webhook_key, api_version]
        if not all(required_values):
            self._clear_shopify_config()
            self._clear_shopify_ids()
            if any(required_values):
                _logger.warning("Shopify overrides incomplete; cleared Shopify configuration.")
            else:
                _logger.info("Shopify overrides missing; cleared Shopify configuration.")
            return

        shop_url_lower = shop_url_key.lower()
        for indicator in production_indicators:
            if indicator and indicator in shop_url_lower:
                raise ValidationError(
                    f"Shopify shop_url_key '{shop_url_key}' appears to be production (indicator: '{indicator}')."
                )

        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("shopify.shop_url_key", shop_url_key)
        parameter_model.set_param("shopify.api_token", api_token)
        parameter_model.set_param("shopify.webhook_key", webhook_key)
        parameter_model.set_param("shopify.api_version", api_version)
        parameter_model.set_param("shopify.test_store", "True" if test_store else "False")
        self._remove_shopify_legacy_keys()

        if test_store:
            self._clear_shopify_ids()

    def _clear_shopify_config(self) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        keys = [
            "shopify.shop_url_key",
            "shopify.api_token",
            "shopify.webhook_key",
            "shopify.api_version",
            "shopify.test_store",
            "shopify.shop_url",
            "shopify.store_url",
        ]
        records = parameter_model.search([("key", "in", keys)])
        if records:
            records.unlink()

    def _remove_shopify_legacy_keys(self) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        legacy_keys = ["shopify.shop_url", "shopify.store_url"]
        records = parameter_model.search([("key", "in", legacy_keys)])
        if records:
            records.unlink()

    def _clear_shopify_ids(self) -> None:
        product_model = self.env["product.product"].sudo().with_context(skip_shopify_sync=True)
        fields_to_clear = [
            "shopify_created_at",
            "shopify_last_exported",
            "shopify_last_exported_at",
            "shopify_condition_id",
            "shopify_variant_id",
            "shopify_product_id",
            "shopify_ebay_category_id",
        ]
        existing_fields = [field for field in fields_to_clear if field in product_model._fields]
        if not existing_fields:
            return
        for field_name in existing_fields:
            self.env.cr.execute(f"UPDATE product_product SET {field_name} = NULL")
