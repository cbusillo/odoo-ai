from odoo import SUPERUSER_ID, api
from odoo.addons.shopify_sync import hooks
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    # noinspection PyProtectedMember
    # Migration relies on internal helper to keep Shopify cleanup logic centralized.
    hooks._migrate_marketplace_external_ids(env)
