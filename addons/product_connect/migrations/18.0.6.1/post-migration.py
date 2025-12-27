from odoo import api, SUPERUSER_ID
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env:
        return

    env["product.image"].remove_missing_images()
