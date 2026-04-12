# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import SUPERUSER_ID, api
from odoo.api import Environment
from odoo.modules.module import get_module_path
from odoo.sql_db import Cursor
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


def _ensure_env(cursor_or_env: Cursor | Environment) -> Environment:
    if isinstance(cursor_or_env, api.Environment):
        return cursor_or_env
    return api.Environment(cursor_or_env, SUPERUSER_ID, {})


@openupgrade.migrate()
def migrate(cr: Cursor, version: str) -> None:
    """Post-migration hook for opw_custom (19.0.8.2)."""
    _ = version
    env = _ensure_env(cr)
    _mark_missing_manifest_modules_uninstalled(env)
