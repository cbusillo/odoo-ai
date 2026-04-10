from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.shopify_sync.migrations.shopify_order_identity import migrate_shipstation_order_identity_external_ids


def migrate(cr: Cursor, version: str) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_shipstation_order_identity_external_ids(env)
