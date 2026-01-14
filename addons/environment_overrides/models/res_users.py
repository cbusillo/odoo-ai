import json
import logging

from odoo import api, models
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.exceptions import AccessDenied, UserError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _resolve_authentik_template_user(self) -> models.Model | None:
        template_user = self.env.ref(
            "environment_overrides.authentik_template_user",
            raise_if_not_found=False,
        )
        if template_user and template_user.exists():
            return template_user
        return None

    def _create_user_from_template(self, values: dict[str, object]) -> models.Model:
        if self.env.context.get("oauth_use_internal_template"):
            template_user = self._resolve_authentik_template_user()
            if template_user:
                if not values.get("login"):
                    raise ValueError(self.env._("Signup: no login given for new user"))
                if not values.get("partner_id") and not values.get("name"):
                    raise ValueError(self.env._("Signup: no name or partner given for new user"))
                values["active"] = True
                return template_user.with_context(no_reset_password=True).copy(values)
            _logger.warning("Authentik template user not found; falling back to default template user.")
        return super()._create_user_from_template(values)

    @api.model
    def _signup_create_user(self, values: dict[str, object]) -> models.Model:
        if self.env.context.get("oauth_use_internal_template"):
            return self._create_user_from_template(values)
        return super()._signup_create_user(values)

    @api.model
    def _auth_oauth_signin(
        self,
        provider: int,
        validation: dict[str, object],
        params: dict[str, str],
    ) -> str | None:
        oauth_uid = validation["user_id"]
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
            return oauth_user.login
        except AccessDenied as access_denied_exception:
            if self.env.context.get("no_user_creation"):
                return None
            state = json.loads(params["state"])
            token = state.get("t")
            values = self._generate_signup_values(provider, validation, params)
            try:
                login, _ = self.with_context(oauth_use_internal_template=True).signup(values, token)
                return login
            except (SignupError, UserError):
                raise access_denied_exception
