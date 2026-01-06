import logging

from odoo import api, SUPERUSER_ID
from odoo.sql_db import Cursor

try:
    from odoo.upgrade import util as upgrade_utils
except ImportError:  # pragma: no cover - Odoo 19 upgrade path
    upgrade_utils = None

_logger = logging.getLogger(__name__)


def _rename_columns(cr: Cursor) -> None:
    if upgrade_utils is not None:
        upgrade_utils.rename_field(cr, "product.image", "index", "initial_index")
        upgrade_utils.rename_field(cr, "motor.image", "index", "initial_index")
        return
    try:
        from openupgradelib import openupgrade
    except ImportError:
        _logger.warning("OpenUpgrade helpers unavailable; skipping column renames.")
        return
    rename_targets = [
        ("product_image", "index", "initial_index"),
        ("motor_image", "index", "initial_index"),
    ]
    for table_name, old_name, new_name in rename_targets:
        if not openupgrade.table_exists(cr, table_name):
            continue
        if not openupgrade.column_exists(cr, table_name, old_name):
            continue
        if openupgrade.column_exists(cr, table_name, new_name):
            continue
        openupgrade.rename_columns(cr, {table_name: [(old_name, new_name)]})


def _remove_fields(cr: Cursor) -> None:
    if upgrade_utils is not None:
        upgrade_utils.remove_field(cr, "product.product", "shopify_last_exported")
        return
    try:
        from openupgradelib import openupgrade
    except ImportError:
        _logger.warning("OpenUpgrade helpers unavailable; skipping field cleanup.")
        return
    openupgrade.drop_columns(cr, [("product_product", "shopify_last_exported")])


def _remove_models(cr: Cursor) -> None:
    if upgrade_utils is not None:
        upgrade_utils.remove_model(cr, "notification.history")
        return
    _logger.warning("Upgrade helpers unavailable; skipping model cleanup for notification.history.")


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

    _rename_columns(cr)
    _remove_fields(cr)
    _remove_models(cr)
