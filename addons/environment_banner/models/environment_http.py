from odoo import api, models

ENVIRONMENT_BANNER_ENABLED_PARAM = "environment_banner.enabled"
ENVIRONMENT_BANNER_PRODUCTION_HOSTNAMES_PARAM = "environment_banner.production_hostnames"

FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}


def _parse_boolean(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def _parse_hostnames(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    parts = raw_value.replace(",", " ").split()
    return [part.strip().lower() for part in parts]


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def session_info(self) -> dict:
        session_info = super().session_info()
        session_info["environment_banner"] = self._get_environment_banner_config()
        return session_info

    def _get_environment_banner_config(self) -> dict:
        parameter_model = self.env["ir.config_parameter"].sudo()
        enabled_raw = parameter_model.get_param(ENVIRONMENT_BANNER_ENABLED_PARAM, "True")
        production_hostnames_raw = parameter_model.get_param(
            ENVIRONMENT_BANNER_PRODUCTION_HOSTNAMES_PARAM,
            "",
        )
        return {
            "enabled": _parse_boolean(enabled_raw, default=True),
            "production_hostnames": _parse_hostnames(production_hostnames_raw),
        }
