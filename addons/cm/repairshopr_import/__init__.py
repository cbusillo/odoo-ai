from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from . import models
from .hooks import post_init_hook
from .models.repairshopr_importer import REPAIRSHOPR_RESUME_STATE_PARAM


def uninstall_hook(cursor: Cursor, registry: object) -> None:
    env = api.Environment(cursor, SUPERUSER_ID, {})
    env["ir.config_parameter"].sudo().set_param(REPAIRSHOPR_RESUME_STATE_PARAM, "")
    external_id_records = env["external.id"].sudo().search([("system_id.code", "=", "repairshopr")])
    if not external_id_records:
        return
    external_id_records.write({"active": False})
    external_id_records.unlink()
