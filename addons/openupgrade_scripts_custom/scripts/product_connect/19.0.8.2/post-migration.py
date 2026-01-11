# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.modules.module import get_module_path
from odoo.orm.environments import Environment
from openupgradelib import openupgrade

_MISSING_MANIFEST_MODULES = (
    "account_auto_transfer",
    "account_disallowed_expenses",
    "sale_async_emails",
    "web_editor",
)


def _mark_missing_manifest_modules_uninstalled(env: Environment) -> None:
    for module_name in _MISSING_MANIFEST_MODULES:
        if get_module_path(module_name):
            continue
        env.cr.execute(
            "UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL, auto_install = FALSE WHERE name = %s",
            (module_name,),
        )


@openupgrade.migrate()
def migrate(env: Environment, _version: str) -> None:
    """Post-migration hook for product_connect (19.0.8.2)."""
    _mark_missing_manifest_modules_uninstalled(env)
