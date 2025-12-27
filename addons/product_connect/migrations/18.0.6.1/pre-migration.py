from odoo import api, SUPERUSER_ID
from odoo.sql_db import Cursor
from odoo.upgrade import util


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env:
        return

    env["ir.config_parameter"].sudo().search([("key", "=", "shopify.last_import_time")]).unlink()

    shop_url_param = env["ir.config_parameter"].sudo().search([("key", "=", "shopify.shop_url")], limit=1)
    if shop_url_param and shop_url_param.value:
        env["ir.config_parameter"].sudo().set_param("shopify.shop_url_key", shop_url_param.value)
    shop_url_param.unlink()

    env["ir.config_parameter"].sudo().search([("key", "=", "shopify.api_version")]).unlink()
    env["ir.cron"].with_context(active_test=False).sudo().search([("name", "=", "Run Shopify Sync")]).unlink()

    util.rename_field(cr, "product.image", "index", "initial_index")
    util.rename_field(cr, "motor.image", "index", "initial_index")

    util.remove_field(cr, "product.product", "shopify_last_exported")

    util.remove_model(cr, "notification.history")
