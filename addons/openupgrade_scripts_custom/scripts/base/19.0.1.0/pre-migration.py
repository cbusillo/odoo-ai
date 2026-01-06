# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.modules.module import get_module_path
from openupgradelib import openupgrade


_MISSING_MANIFEST_MODULES = (
    "account_auto_transfer",
    "account_disallowed_expenses",
    "sale_async_emails",
    "web_editor",
)


def _mark_missing_manifest_modules_uninstalled(env) -> None:
    """Avoid inconsistent module states for addons removed in 19.0.

    These modules can exist as installed records in the restored 18.0 database,
    but are absent from the 19.0 addons paths (no manifest). Mark them
    uninstalled before module graph processing.
    """

    for module_name in _MISSING_MANIFEST_MODULES:
        module_path = get_module_path(module_name)
        if module_path:
            continue
        env.cr.execute(
            "UPDATE ir_module_module "
            "SET state = 'uninstalled', latest_version = NULL, auto_install = FALSE "
            "WHERE name = %s",
            (module_name,),
        )


@openupgrade.migrate()
def migrate(env, version):
    """Pre-migration hook for base (19.0.1.0)."""

    _mark_missing_manifest_modules_uninstalled(env)
