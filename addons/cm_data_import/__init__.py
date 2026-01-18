from odoo import SUPERUSER_ID, api

from . import models
from .hooks import post_init_hook


def uninstall_hook(cursor, registry) -> None:
    env = api.Environment(cursor, SUPERUSER_ID, {})
    external_id_records = env["external.id"].sudo().search([("system_id.code", "=", "cm_data")])
    if not external_id_records:
        return
    external_id_records.write({"active": False})
    external_id_records.unlink()
