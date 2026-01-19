import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def _schedule_repairshopr_import(environment: "api.Environment", *, reason: str) -> None:
    cron = environment.ref("repairshopr_import.ir_cron_repairshopr_import", raise_if_not_found=False)
    cron = cron.exists() if cron else environment["ir.cron"]
    if not cron:
        _logger.warning("RepairShopr cron not found during %s hook", reason)
        return
    cron.sudo().write({
        "active": True,
        "nextcall": fields.Datetime.now(),
    })


def post_init_hook(environment: "api.Environment") -> None:
    environment["repairshopr.importer"].sudo()._get_repairshopr_system()
    _schedule_repairshopr_import(environment, reason="post_init")


def schedule_after_update(cursor, _version) -> None:
    environment = api.Environment(cursor, SUPERUSER_ID, {})
    _schedule_repairshopr_import(environment, reason="post_migration")
