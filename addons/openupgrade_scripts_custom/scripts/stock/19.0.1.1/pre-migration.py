# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from typing import TYPE_CHECKING

from openupgradelib import openupgrade

if TYPE_CHECKING:
    from odoo.api import Environment


def _ensure_scheduler_server_action(env: "Environment") -> None:
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


@openupgrade.migrate()
def migrate(env: "Environment", version: str | None) -> None:
    """Pre-migration hook for stock (19.0.1.1)."""
    _ensure_scheduler_server_action(env)
