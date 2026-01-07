# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
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


def _clean_user_group_views(env) -> None:
    """Normalize legacy user group fields before the 19.0 view update."""

    candidate_xmlids = ("user_groups_view", "view_users_form")

    def _fetch_view_id(xmlid_name: str) -> int | None:
        env.cr.execute(
            "SELECT res_id FROM ir_model_data "
            "WHERE module = 'base' AND name = %s AND model = 'ir.ui.view' "
            "LIMIT 1",
            (xmlid_name,),
        )
        view_row = env.cr.fetchone()
        if not view_row:
            return None
        return view_row[0]

    def _normalize_view_text(view_text: str) -> str:
        updated_text = view_text.replace('name="groups_id"', 'name="group_ids"')
        updated_text = updated_text.replace("name='groups_id'", "name='group_ids'")
        updated_text = re.sub(r"<field[^>]+name=\"(sel_groups_|in_group_)[^\"]+\"[^>]*/>", "", updated_text)
        updated_text = re.sub(r"<field[^>]+name='(sel_groups_|in_group_)[^']+'[^>]*/>", "", updated_text)
        updated_text = re.sub(
            r"<field[^>]+name=\"(sel_groups_|in_group_)[^\"]+\"[^>]*>\s*</field>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(
            r"<field[^>]+name='(sel_groups_|in_group_)[^']+'[^>]*>\s*</field>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(r"<field[^>]+name=\"user_group_warning\"[^>]*/>", "", updated_text)
        updated_text = re.sub(r"<field[^>]+name='user_group_warning'[^>]*/>", "", updated_text)
        updated_text = re.sub(
            r"<field[^>]+name=\"user_group_warning\"[^>]*>\s*</field>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(
            r"<field[^>]+name='user_group_warning'[^>]*>\s*</field>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        return updated_text

    for xmlid_name in candidate_xmlids:
        view_id = _fetch_view_id(xmlid_name)
        if view_id is None:
            continue
        env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view_id,))
        arch_row = env.cr.fetchone()
        if not arch_row:
            continue
        view_arch = arch_row[0] or ""

        if isinstance(view_arch, dict):
            updated_payload = {locale: _normalize_view_text(text) for locale, text in view_arch.items()}
            if updated_payload == view_arch:
                continue
            env.cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(updated_payload), view_id))
            continue

        if isinstance(view_arch, str):
            try:
                parsed_payload = json.loads(view_arch)
            except json.JSONDecodeError:
                parsed_payload = None
            if isinstance(parsed_payload, dict):
                updated_payload = {locale: _normalize_view_text(text) for locale, text in parsed_payload.items()}
                if updated_payload == parsed_payload:
                    continue
                env.cr.execute(
                    "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                    (json.dumps(updated_payload), view_id),
                )
                continue

        updated_arch = _normalize_view_text(str(view_arch))
        if updated_arch == str(view_arch):
            continue
        env.cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (updated_arch, view_id))


@openupgrade.migrate()
def migrate(env, version):
    """Pre-migration hook for base (19.0.1.0)."""

    _mark_missing_manifest_modules_uninstalled(env)
    _clean_user_group_views(env)
