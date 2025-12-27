from odoo import api, SUPERUSER_ID

from odoo.sql_db import Cursor
from odoo.upgrade import util


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env:
        return

    util.remove_column(cr, "motor", "technician")
    util.remove_column(cr, "res_users", "is_technician")
    util.remove_model(cr, "product.import.image.wizard")
    util.remove_model(cr, "product.import.image")
    util.remove_model(cr, "motor.product.image")
