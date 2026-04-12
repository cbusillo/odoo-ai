# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import SUPERUSER_ID, api
from odoo.api import Environment
from odoo.sql_db import Cursor
from openupgradelib import openupgrade


def _ensure_scheduler_server_action(env: Environment) -> None:
    model_data = env["ir.model.data"].search(
        [
            ("module", "=", "stock"),
            ("name", "=", "ir_cron_scheduler_action_ir_actions_server"),
            ("model", "=", "ir.actions.server"),
        ],
        limit=1,
    )
    action_record = None
    if model_data:
        action_record = env["ir.actions.server"].browse(model_data.res_id).exists()
    if action_record:
        return
    stock_rule_model = env["ir.model"].search([("model", "=", "stock.rule")], limit=1)
    if not stock_rule_model:
        return
    action_record = env["ir.actions.server"].create(
        {
            "name": "Procurement: run scheduler",
            "type": "ir.actions.server",
            "model_id": stock_rule_model.id,
            "state": "code",
            "code": "model.run_scheduler(True)",
        }
    )
    if model_data:
        model_data.write({"res_id": action_record.id})
    else:
        env["ir.model.data"].create(
            {
                "module": "stock",
                "name": "ir_cron_scheduler_action_ir_actions_server",
                "model": "ir.actions.server",
                "res_id": action_record.id,
                "noupdate": True,
            }
        )


def _ensure_env(cursor_or_env: Cursor | Environment) -> Environment:
    if isinstance(cursor_or_env, api.Environment):
        return cursor_or_env
    return api.Environment(cursor_or_env, SUPERUSER_ID, {})


@openupgrade.migrate()
def migrate(cr: Cursor, version: str | None) -> None:
    """Pre-migration hook for stock (19.0.1.1)."""
    _ = version
    env = _ensure_env(cr)
    _ensure_scheduler_server_action(env)
