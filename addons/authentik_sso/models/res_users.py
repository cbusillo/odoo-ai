import html
import json
import logging
import os

from odoo import Command, api, models
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.exceptions import AccessDenied, UserError

_logger = logging.getLogger(__name__)

AUTHENTIK_PREFIX = "ENV_OVERRIDE_AUTHENTIK__"
DEFAULT_AUTHENTIK_PROVIDER_NAME = "Authentik"
DEFAULT_AUTHENTIK_GROUP_CLAIM = "groups"
DEFAULT_AUTHENTIK_USER_ID_CLAIMS = ("user_id", "sub", "id", "uid")
DEFAULT_AUTHENTIK_LOGIN_CLAIMS = ("email", "preferred_username", "username", "login")
DEFAULT_AUTHENTIK_NAME_CLAIMS = (
    "name",
    "full_name",
    "display_name",
    "preferred_username",
    "username",
    "email",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _resolve_authentik_template_user(self) -> "odoo.model.res_users":
        template_user = self.env.ref(
            "authentik_sso.authentik_template_user",
            raise_if_not_found=False,
        )
        return template_user.exists() if template_user else self.env["res.users"]

    def _create_user_from_template(self, values: dict[str, object]) -> "odoo.model.res_users":
        if self.env.context.get("oauth_use_internal_template"):
            template_user = self._resolve_authentik_template_user()
            if template_user:
                if not values.get("login"):
                    raise ValueError(self.env._("Signup: no login given for new user"))
                if not values.get("partner_id") and not values.get("name"):
                    raise ValueError(self.env._("Signup: no name or partner given for new user"))
                if "signature" not in values:
                    signature_name = values.get("name")
                    if signature_name:
                        safe_name = html.escape(str(signature_name))
                        values["signature"] = f"<div>{safe_name}</div>"
                    else:
                        values["signature"] = False
                values["active"] = True
                return template_user.with_context(no_reset_password=True).copy(values)
            _logger.warning("Authentik template user not found; falling back to default template user.")
        return super()._create_user_from_template(values)

    @api.model
    def _signup_create_user(self, values: dict[str, object]) -> "odoo.model.res_users":
        if self.env.context.get("oauth_use_internal_template"):
            return self._create_user_from_template(values)
        return super()._signup_create_user(values)

    @staticmethod
    def _authentik_provider_name() -> str:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}PROVIDER_NAME")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_PROVIDER_NAME
        cleaned = raw_value.strip()
        return cleaned or DEFAULT_AUTHENTIK_PROVIDER_NAME

    @staticmethod
    def _authentik_group_claim() -> str:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}GROUP_CLAIM")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_GROUP_CLAIM
        return raw_value.strip()

    @staticmethod
    def _authentik_user_id_claims() -> tuple[str, ...]:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}USER_ID_CLAIMS")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_USER_ID_CLAIMS
        cleaned = tuple(item.strip() for item in raw_value.split(",") if item.strip())
        return cleaned or DEFAULT_AUTHENTIK_USER_ID_CLAIMS

    @staticmethod
    def _authentik_login_claims() -> tuple[str, ...]:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}LOGIN_CLAIMS")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_LOGIN_CLAIMS
        cleaned = tuple(item.strip() for item in raw_value.split(",") if item.strip())
        return cleaned or DEFAULT_AUTHENTIK_LOGIN_CLAIMS

    @staticmethod
    def _authentik_name_claims() -> tuple[str, ...]:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}NAME_CLAIMS")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_NAME_CLAIMS
        return tuple(item.strip() for item in raw_value.split(",") if item.strip())

    @staticmethod
    def _claim_to_string(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        if isinstance(value, (list, tuple)) and value:
            first = value[0]
            if isinstance(first, str):
                cleaned = first.strip()
                return cleaned or None
        return None

    def _first_claim_value(self, payload: dict[str, object], claims: tuple[str, ...]) -> str | None:
        for claim in claims:
            value = self._claim_to_string(payload.get(claim))
            if value:
                return value
        return None

    def _normalize_authentik_validation(self, validation: dict[str, object]) -> dict[str, object]:
        normalized = dict(validation)
        user_id_value = self._first_claim_value(normalized, self._authentik_user_id_claims())
        if user_id_value:
            normalized.setdefault("user_id", user_id_value)

        login_value = self._first_claim_value(normalized, self._authentik_login_claims())
        if not login_value and user_id_value:
            login_value = user_id_value
        if login_value:
            normalized.setdefault("login", login_value)
            if "@" in login_value and not normalized.get("email"):
                normalized["email"] = login_value

        if not normalized.get("name"):
            given_name = self._claim_to_string(normalized.get("given_name"))
            family_name = self._claim_to_string(normalized.get("family_name"))
            combined_name = " ".join(part for part in (given_name, family_name) if part)
            if combined_name:
                normalized["name"] = combined_name
        if not normalized.get("name"):
            name_value = self._first_claim_value(normalized, self._authentik_name_claims())
            if name_value:
                normalized["name"] = name_value
        if not normalized.get("name") and normalized.get("login"):
            normalized["name"] = normalized["login"]

        return normalized

    def _extract_authentik_groups(self, validation: dict[str, object]) -> set[str]:
        claim_key = self._authentik_group_claim()
        if not claim_key:
            return set()
        raw_groups = validation.get(claim_key)
        if not raw_groups:
            return set()
        if isinstance(raw_groups, str):
            candidates = [raw_groups]
        elif isinstance(raw_groups, (list, tuple, set)):
            candidates = [str(item) for item in raw_groups]
        else:
            return set()
        cleaned = {item.strip() for item in candidates if item and item.strip()}
        return cleaned

    def _sync_authentik_groups(
        self,
        oauth_user: "odoo.model.res_users",
        validation: dict[str, object],
        provider_id: int,
    ) -> None:
        provider = self.env["auth.oauth.provider"].sudo().browse(provider_id)
        if not provider or not provider.exists():
            return
        if provider.name != self._authentik_provider_name():
            return
        group_names = self._extract_authentik_groups(validation)
        mapping_model = self.env["authentik.sso.group.mapping"].sudo()
        mappings = mapping_model.search([("active", "=", True)], order="sequence, id")
        if not mappings:
            _logger.warning("Authentik group mapping skipped; no mappings configured.")
            return

        normalized_groups = {name.casefold() for name in group_names}
        matching_mappings = mapping_model.browse()
        if normalized_groups:
            for mapping in mappings:
                if mapping.is_fallback:
                    continue
                authentik_group = (mapping.authentik_group or "").casefold()
                if authentik_group and authentik_group in normalized_groups:
                    matching_mappings |= mapping
        else:
            fallback = mappings.filtered("is_fallback")
            if fallback:
                matching_mappings = fallback

        target_group_ids = set(matching_mappings.mapped("odoo_groups").ids)
        base_user_group = self.env.ref("base.group_user", raise_if_not_found=False)
        base_user_group = base_user_group.exists() if base_user_group else self.env["res.groups"]
        if base_user_group:
            target_group_ids.add(base_user_group.id)
        else:
            _logger.warning("Authentik group mapping skipped; base user group not found.")
            return

        managed_group_ids = set(mappings.mapped("odoo_groups").ids)
        commands = [Command.link(group_id) for group_id in target_group_ids]
        for group_id in managed_group_ids - target_group_ids:
            commands.append(Command.unlink(group_id))

        oauth_user.sudo().write({"group_ids": commands})

    @api.model
    def _auth_oauth_signin(
        self,
        provider: int,
        validation: dict[str, object],
        params: dict[str, str],
    ) -> str | None:
        provider_record = self.env["auth.oauth.provider"].sudo().browse(provider)
        if provider_record and provider_record.exists() and provider_record.name == self._authentik_provider_name():
            normalized_validation = self._normalize_authentik_validation(validation)
        else:
            normalized_validation = validation

        oauth_uid = normalized_validation.get("user_id")
        if not oauth_uid:
            _logger.warning(
                "OAuth validation missing user_id claim. Keys=%s",
                ", ".join(sorted(normalized_validation.keys())),
            )
            raise AccessDenied()
        oauth_uid = str(oauth_uid)
        try:
            oauth_user = self.search(
                [
                    ("oauth_uid", "=", oauth_uid),
                    ("oauth_provider_id", "=", provider),
                ]
            )
            if not oauth_user:
                raise AccessDenied()
            assert len(oauth_user) == 1
            oauth_user.write({"oauth_access_token": params["access_token"]})
            self._sync_authentik_groups(oauth_user, normalized_validation, provider)
            return oauth_user.login
        except AccessDenied as access_denied_exception:
            if self.env.context.get("no_user_creation"):
                return None
            state = json.loads(params["state"])
            token = state.get("t")
            values = self._generate_signup_values(provider, normalized_validation, params)
            try:
                login, _ = self.with_context(oauth_use_internal_template=True).signup(values, token)
                created_user = self.search([("login", "=", login)], limit=1)
                if created_user:
                    self._sync_authentik_groups(created_user, normalized_validation, provider)
                return login
            except (SignupError, UserError) as error:
                _logger.warning(
                    "OAuth signup failed for provider %s. Validation keys=%s",
                    provider,
                    ", ".join(sorted(normalized_validation.keys())),
                )
                raise access_denied_exception from error
