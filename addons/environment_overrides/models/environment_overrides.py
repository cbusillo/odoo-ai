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
        test_store = _parse_boolean(test_store_raw, default=False)

        indicators_raw = os.environ.get(f"{SHOPIFY_PREFIX}PRODUCTION_INDICATORS")
        if indicators_raw is None:
            production_indicators = list(DEFAULT_PRODUCTION_INDICATORS)
        else:
            cleaned = [item.strip().lower() for item in indicators_raw.split(",") if item.strip()]
            production_indicators = cleaned or list(DEFAULT_PRODUCTION_INDICATORS)

        required_values = [shop_url_key, api_token, webhook_key, api_version]
        if not all(required_values):
            self._clear_shopify_config()
            if any(required_values):
                _logger.warning("Shopify overrides incomplete; cleared Shopify configuration.")
            else:
                _logger.info("Shopify overrides missing; cleared Shopify configuration.")
            return

        shop_url_lower = shop_url_key.lower()
        for indicator in production_indicators:
            if indicator and indicator in shop_url_lower:
                raise ValidationError(f"Shopify shop_url_key '{shop_url_key}' appears to be production (indicator: '{indicator}').")

        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("shopify.shop_url_key", shop_url_key)
        parameter_model.set_param("shopify.api_token", api_token)
        parameter_model.set_param("shopify.webhook_key", webhook_key)
        parameter_model.set_param("shopify.api_version", api_version)
        parameter_model.set_param("shopify.test_store", "True" if test_store else "False")
        self._remove_shopify_legacy_keys()
        self._update_shopify_external_urls(shop_url_key)

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

    @staticmethod
    def _normalize_shopify_storefront_base(shop_url_key: str) -> str:
        from urllib.parse import urlsplit

        raw_value = (shop_url_key or "").strip().strip("/")
        if not raw_value:
            return ""

        lower_value = raw_value.lower()
        http_prefix = "http" + "://"
        https_prefix = "https" + "://"
        if lower_value.startswith(http_prefix) or lower_value.startswith(https_prefix):
            parts = urlsplit(raw_value)
            netloc = parts.netloc
            if not netloc:
                return ""
            return f"{parts.scheme}://{netloc}"

        raw_value = raw_value.split("/", 1)[0]
        raw_value = raw_value.split("?", 1)[0].split("#", 1)[0]
        if raw_value.endswith(".myshopify.com"):
            return f"https://{raw_value}"
        if "." in raw_value:
            return f"https://{raw_value}"
        return f"https://{raw_value}.myshopify.com"

    @staticmethod
    def _derive_shopify_admin_store_key(shop_url_key: str) -> str:
        from urllib.parse import urlsplit

        raw_value = (shop_url_key or "").strip().strip("/")
        if not raw_value:
            return ""

        lower_value = raw_value.lower()
        http_prefix = "http" + "://"
        https_prefix = "https" + "://"
        if lower_value.startswith(http_prefix) or lower_value.startswith(https_prefix):
            parts = urlsplit(raw_value)
            host = parts.netloc
        else:
            host = raw_value.split("/", 1)[0]
        host = host.split("?", 1)[0].split("#", 1)[0]

        if host.endswith(".myshopify.com"):
            return host.split(".", 1)[0]
        if "." in host:
            return ""
        return host

    def _update_shopify_external_urls(self, shop_url_key: str) -> None:
        external_system_model = self.env.get("external.system")
        external_system_url_model = self.env.get("external.system.url")
        if external_system_model is None or external_system_url_model is None:
            return

        system = external_system_model.sudo().search([("code", "=", "shopify")], limit=1)
        if not system:
            return

        storefront_base = self._normalize_shopify_storefront_base(shop_url_key)
        admin_store_key = self._derive_shopify_admin_store_key(shop_url_key)
        admin_base = f"https://admin.shopify.com/store/{admin_store_key}" if admin_store_key else ""

        system_url = system["url"] if "url" in system._fields else ""
        if storefront_base and system_url != storefront_base:
            system.write({"url": storefront_base})

        url_templates = external_system_url_model.sudo().search(
            [
                ("system_id", "=", system.id),
                ("code", "in", ["customer_admin", "product_admin", "product_store"]),
            ]
        )
        for url_template in url_templates:
            url_code = url_template["code"] if "code" in url_template._fields else ""
            if url_code in {"customer_admin", "product_admin"}:
                base_url = admin_base
            else:
                base_url = storefront_base
            if not base_url:
                continue
            template_base_url = url_template["base_url"] if "base_url" in url_template._fields else ""
            if template_base_url != base_url:
                url_template.write({"base_url": base_url})
