import logging
import os

from odoo import models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

AUTHENTIK_PREFIX = "ENV_OVERRIDE_AUTHENTIK__"


DEFAULT_PROVIDER_NAME = "Authentik"
DEFAULT_SCOPE = "openid profile email"
DEFAULT_LOGIN_LABEL = "Sign in with Authentik"
DEFAULT_CSS_CLASS = "fa fa-fw fa-sign-in text-primary"


def _split_list(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _normalize_base_url(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    cleaned = raw_value.strip().rstrip("/")
    return cleaned or None


class AuthentikSsoConfig(models.AbstractModel):
    _name = "authentik.sso.config"
    _description = "Authentik SSO configuration"

    def apply_from_env(self) -> None:
        self._disable_oauth_providers()
        self._apply_authentik_provider()

    def _disable_oauth_providers(self) -> None:
        disabled_raw = os.environ.get(f"{AUTHENTIK_PREFIX}DISABLE_PROVIDERS")
        disabled_names = _split_list(disabled_raw)
        if not disabled_names:
            return
        provider_model = self.env["auth.oauth.provider"].sudo()
        providers = provider_model.search([])
        if not providers:
            return
        lowered_terms = {term.casefold() for term in disabled_names}
        to_disable = provider_model.browse()
        for provider in providers:
            provider_name = (provider.name or "").casefold()
            if provider_name in lowered_terms:
                to_disable |= provider
                continue
            auth_endpoint = (provider.auth_endpoint or "").casefold()
            if any(term in auth_endpoint for term in lowered_terms):
                to_disable |= provider

        if not to_disable:
            return
        to_disable.write({"enabled": False})
        _logger.info("Disabled OAuth providers: %s", ", ".join(sorted(to_disable.mapped("name"))))

    def _apply_authentik_provider(self) -> None:
        provider_name = os.environ.get(f"{AUTHENTIK_PREFIX}PROVIDER_NAME", DEFAULT_PROVIDER_NAME).strip()
        if not provider_name:
            provider_name = DEFAULT_PROVIDER_NAME
        client_id = os.environ.get(f"{AUTHENTIK_PREFIX}CLIENT_ID", "").strip()
        base_url = _normalize_base_url(os.environ.get(f"{AUTHENTIK_PREFIX}BASE_URL"))
        authorization_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}AUTHORIZATION_ENDPOINT", "").strip()
        userinfo_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}USERINFO_ENDPOINT", "").strip()
        scope = os.environ.get(f"{AUTHENTIK_PREFIX}SCOPE", DEFAULT_SCOPE).strip()
        login_label = os.environ.get(f"{AUTHENTIK_PREFIX}LOGIN_LABEL", DEFAULT_LOGIN_LABEL).strip()
        css_class = os.environ.get(f"{AUTHENTIK_PREFIX}CSS_CLASS", DEFAULT_CSS_CLASS).strip()
        data_endpoint = os.environ.get(f"{AUTHENTIK_PREFIX}DATA_ENDPOINT", "").strip()

        if base_url:
            if not authorization_endpoint:
                authorization_endpoint = f"{base_url}/application/o/authorize/"
            if not userinfo_endpoint:
                userinfo_endpoint = f"{base_url}/application/o/userinfo/"
            if not data_endpoint:
                data_endpoint = f"{base_url}/application/o/token/"

        provider_model = self.env["auth.oauth.provider"].sudo()
        provider = provider_model.search([("name", "=", provider_name)], limit=1)

        required_missing = not client_id or not base_url or not authorization_endpoint or not userinfo_endpoint
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

        values: "odoo.values.auth_oauth_provider" = {
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
