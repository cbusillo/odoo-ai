import logging
import os

from odoo import models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

CONFIG_PARAM_PREFIX = "ENV_OVERRIDE_CONFIG_PARAM__"
AUTHENTIK_PREFIX = "ENV_OVERRIDE_AUTHENTIK__"
SHOPIFY_PREFIX = "ENV_OVERRIDE_SHOPIFY__"

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

    def _apply_authentik_overrides(self) -> None:
        provider_name = os.environ.get(f"{AUTHENTIK_PREFIX}PROVIDER_NAME", "Authentik").strip()
        client_id = os.environ.get(f"{AUTHENTIK_PREFIX}CLIENT_ID", "").strip()
        client_secret_raw = os.environ.get(f"{AUTHENTIK_PREFIX}CLIENT_SECRET")
        client_secret = client_secret_raw.strip() if client_secret_raw is not None else None
        authorization_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}AUTHORIZATION_ENDPOINT", "").strip()
        userinfo_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}USERINFO_ENDPOINT", "").strip()
        scope = os.environ.get(f"{AUTHENTIK_PREFIX}SCOPE", "openid profile email").strip()
        login_label = os.environ.get(f"{AUTHENTIK_PREFIX}LOGIN_LABEL", "Sign in with Authentik").strip()
        css_class = os.environ.get(f"{AUTHENTIK_PREFIX}CSS_CLASS", "fa fa-fw fa-sign-in text-primary").strip()
        data_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}DATA_ENDPOINT", "").strip()

        provider_model = self.env["auth.oauth.provider"].sudo()
        provider = provider_model.search([("name", "=", provider_name)], limit=1)

        required_missing = not client_id or not authorization_endpoint or not userinfo_endpoint
        if required_missing:
            if provider:
                provider.write(
                    {
                        "enabled": False,
                        "client_id": False,
                        "auth_endpoint": False,
                        "validation_endpoint": False,
                        "data_endpoint": False,
                        "scope": False,
                        "css_class": False,
                        "body": False,
                    }
                )
                _logger.info("Authentik overrides missing; disabled provider '%s'.", provider_name)
            else:
                _logger.info("Authentik overrides missing; provider '%s' not found.", provider_name)
            return

        values = {
            "name": provider_name,
            "client_id": client_id,
            "auth_endpoint": authorization_endpoint,
            "validation_endpoint": userinfo_endpoint,
            "data_endpoint": data_endpoint or False,
            "scope": scope,
            "enabled": True,
            "css_class": css_class,
            "body": login_label,
        }
        if client_secret is not None:
            values["client_secret"] = client_secret or False
        try:
            if provider:
                provider.write(values)
                _logger.info("Updated Authentik provider '%s'.", provider_name)
            else:
                provider_model.create({**values, "sequence": 10})
                _logger.info("Created Authentik provider '%s'.", provider_name)
        except (AccessError, UserError, ValidationError, ValueError):  # pragma: no cover - defensive logging
            _logger.exception("Failed to apply Authentik overrides; disabling provider if present.")
            if provider:
                try:
                    provider.write({"enabled": False})
                except (AccessError, UserError, ValidationError, ValueError):  # pragma: no cover - best-effort disable
                    _logger.exception("Failed to disable Authentik provider after error.")

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
