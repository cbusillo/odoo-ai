import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def _schedule_cm_data_import(environment: "api.Environment", *, reason: str) -> None:
    cron = environment.ref("cm_data_import.ir_cron_cm_data_import", raise_if_not_found=False)
    cron = cron.exists() if cron else environment["ir.cron"]
    if not cron:
        _logger.warning("CM data cron not found during %s hook", reason)
        return
    cron.sudo().write(
        {
            "active": True,
            "nextcall": fields.Datetime.now(),
        }
    )


def post_init_hook(environment: "api.Environment") -> None:
    environment["integration.cm_data.importer"].sudo()._get_cm_data_system()
    environment["integration.cm_seed.loader"].sudo().run_seed()
    _schedule_cm_data_import(environment, reason="post_init")


def schedule_after_update(cursor, _version) -> None:
    environment = api.Environment(cursor, SUPERUSER_ID, {})
    _schedule_cm_data_import(environment, reason="post_migration")
