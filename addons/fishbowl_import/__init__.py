from odoo import api, SUPERUSER_ID

from . import models
from .hooks import post_init_hook


def uninstall_hook(cr, registry) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    external_id_records = env["external.id"].sudo().search([("system_id.code", "=", "fishbowl")])
    if not external_id_records:
        return
    external_id_records.write({"active": False})
    external_id_records.unlink()
