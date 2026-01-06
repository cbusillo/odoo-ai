import logging

from odoo import api, SUPERUSER_ID
from odoo.sql_db import Cursor

try:
    from odoo.upgrade import util as upgrade_utils
except ImportError:  # pragma: no cover - Odoo 19 upgrade path
    upgrade_utils = None

_logger = logging.getLogger(__name__)


def _remove_columns(cr: Cursor) -> None:
    if upgrade_utils is not None:
        upgrade_utils.remove_column(cr, "motor", "technician")
        upgrade_utils.remove_column(cr, "res_users", "is_technician")
        return
    try:
        from openupgradelib import openupgrade
    except ImportError:
        _logger.warning("OpenUpgrade helpers unavailable; skipping column cleanup.")
        return
    openupgrade.drop_columns(cr, [("motor", "technician"), ("res_users", "is_technician")])


def _remove_models(cr: Cursor) -> None:
    models_to_remove = [
        "product.import.image.wizard",
        "product.import.image",
        "motor.product.image",
    ]
    if upgrade_utils is not None:
        for model_name in models_to_remove:
            upgrade_utils.remove_model(cr, model_name)
        return
    _logger.warning(
        "Upgrade helpers unavailable; skipping model cleanup for %s.",
        ", ".join(models_to_remove),
    )


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env:
        return

    _remove_columns(cr)
    _remove_models(cr)
