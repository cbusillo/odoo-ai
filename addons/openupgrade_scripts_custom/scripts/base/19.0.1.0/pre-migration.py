# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

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


def _clean_user_groups_view(env) -> None:
    """Normalize legacy user group fields before the 19.0 view update."""

    view_record = env.ref("base.user_groups_view", raise_if_not_found=False)
    if not view_record:
        return
    view_arch = view_record.arch_db or ""
    if "groups_id" not in view_arch and "sel_groups_" not in view_arch and "in_group_" not in view_arch:
        return
    updated_arch = view_arch.replace('name="groups_id"', 'name="group_ids"')
    updated_arch = updated_arch.replace("name='groups_id'", "name='group_ids'")
    updated_arch = re.sub(r"<field[^>]+name=\"(sel_groups_|in_group_)[^\"]+\"[^>]*/>", "", updated_arch)
    updated_arch = re.sub(r"<field[^>]+name='(sel_groups_|in_group_)[^']+'[^>]*/>", "", updated_arch)
    updated_arch = re.sub(
        r"<field[^>]+name=\"(sel_groups_|in_group_)[^\"]+\"[^>]*>\s*</field>",
        "",
        updated_arch,
        flags=re.DOTALL,
    )
    updated_arch = re.sub(
        r"<field[^>]+name='(sel_groups_|in_group_)[^']+'[^>]*>\s*</field>",
        "",
        updated_arch,
        flags=re.DOTALL,
    )
    if updated_arch == view_arch:
        return
    view_record.write({"arch_db": updated_arch})


@openupgrade.migrate()
def migrate(env, version):
    """Pre-migration hook for base (19.0.1.0)."""

    _mark_missing_manifest_modules_uninstalled(env)
    _clean_user_groups_view(env)
