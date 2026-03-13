from odoo import SUPERUSER_ID, api

from . import models
from .hooks import post_init_hook


def uninstall_hook(cr: object, registry: object) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.config_parameter"].sudo().set_param("fishbowl.resume_state", "")
    external_id_records = env["external.id"].sudo().search([("system_id.code", "=", "fishbowl")])
    if not external_id_records:
        return
    external_id_records.write({"active": False})
    external_id_records.unlink()
