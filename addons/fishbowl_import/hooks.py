import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def _schedule_fishbowl_import(env: "api.Environment", *, reason: str) -> None:
    cron = env.ref("fishbowl_import.ir_cron_fishbowl_import", raise_if_not_found=False)
    if not cron:
        _logger.warning("Fishbowl cron not found during %s hook", reason)
        return
    cron.sudo().write({
        "active": True,
        "nextcall": fields.Datetime.now(),
    })


def post_init_hook(env: "api.Environment") -> None:
    _schedule_fishbowl_import(env, reason="post_init")


def schedule_after_update(cr, _version) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    _schedule_fishbowl_import(env, reason="post_migration")
