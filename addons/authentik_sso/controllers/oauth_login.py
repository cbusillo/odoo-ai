import base64
import json
import logging
import os

import werkzeug.urls
import werkzeug.utils
from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.addons.auth_oauth.controllers.main import OAuthLogin as BaseOAuthLogin
from odoo.addons.web.controllers.utils import ensure_db
from odoo.http import request

_logger = logging.getLogger(__name__)

AUTHENTIK_PREFIX = "ENV_OVERRIDE_AUTHENTIK__"
DEFAULT_AUTHENTIK_PROVIDER_NAME = "Authentik"


def _authentik_provider_name() -> str:
    raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}PROVIDER_NAME")
    if raw_value is None:
        return DEFAULT_AUTHENTIK_PROVIDER_NAME
    cleaned = raw_value.strip()
    return cleaned or DEFAULT_AUTHENTIK_PROVIDER_NAME


def _build_authentik_auth_link(
    provider: dict[str, object],
    state: dict[str, object],
    redirect_url: str,
) -> str:
    nonce_bytes = base64.urlsafe_b64encode(os.urandom(16))
    nonce = nonce_bytes.decode().rstrip("=")
    params = {
        "response_type": "id_token token",
        "client_id": provider["client_id"],
        "redirect_uri": redirect_url,
        "scope": provider["scope"],
        "state": json.dumps(state),
        "nonce": nonce,
    }
    return f"{provider['auth_endpoint']}?{werkzeug.urls.url_encode(params)}"


def _build_oauth_state(provider_id: int) -> dict[str, object]:
    redirect = request.params.get("redirect") or "web"
    if not redirect.startswith(("//", "http://", "https://")):
        redirect = f"{request.httprequest.url_root}{redirect[1:] if redirect[0] == '/' else redirect}"
    state = {
        "d": request.session.db,
        "p": provider_id,
        "r": werkzeug.urls.url_quote_plus(redirect),
    }
    token = request.params.get("token")
    if token:
        state["t"] = token
    return state


class AuthentikOAuthLogin(BaseOAuthLogin):
    def list_providers(self) -> list[dict[str, object]]:
        providers = super().list_providers()
        if not providers:
            return providers
        authentik_provider_name = _authentik_provider_name()
        for provider in providers:
            if provider.get("name") != authentik_provider_name:
                continue
            auth_endpoint = provider.get("auth_endpoint")
            client_id = provider.get("client_id")
            scope = provider.get("scope")
            if not auth_endpoint or not client_id or not scope:
                _logger.warning(
                    "Authentik provider missing required values; leaving auth_link unchanged.",
                )
                continue
            redirect_url = request.httprequest.url_root + "auth_oauth/signin"
            state = self.get_state(provider)
            provider["auth_link"] = _build_authentik_auth_link(provider, state, redirect_url)
        return providers

    @http.route()
    def web_login(self, *args: object, **kwargs: object) -> object:
        return super().web_login(*args, **kwargs)

    @http.route("/authentik/login", type="http", auth="none", sitemap=False)
    def authentik_login(self, **kwargs: object) -> object:
        ensure_db()
        provider_name = _authentik_provider_name()
        provider = (
            request.env["auth.oauth.provider"]
            .sudo()
            .search(
                [
                    ("enabled", "=", True),
                    ("name", "=", provider_name),
                ],
                limit=1,
            )
        )
        if not provider:
            raise BadRequest()
        state = _build_oauth_state(provider.id)
        redirect_url = request.httprequest.url_root + "auth_oauth/signin"
        provider_data = {
            "auth_endpoint": provider.auth_endpoint,
            "client_id": provider.client_id,
            "scope": provider.scope,
            "name": provider.name,
        }
        auth_link = _build_authentik_auth_link(provider_data, state, redirect_url)
        return werkzeug.utils.redirect(auth_link, 303)
