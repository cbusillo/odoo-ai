import ast
import csv
import json
import logging
import re
from pathlib import Path

from odoo import SUPERUSER_ID, api
from odoo.api import Environment
from odoo.modules.module import get_module_path
from odoo.sql_db import Cursor
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

_MISSING_MANIFEST_MODULES = (
    "account_auto_transfer",
    "account_disallowed_expenses",
    "sale_async_emails",
    "web_editor",
)
LEGACY_MODULE = "product_connect"
RENAMED_MODULE = "opw_custom"
MOVED_MODULES = (
    "marine_motors",
    "notification_center",
    "product_metadata",
    "transaction_utilities",
    "image_enhancements",
    "shopify_sync",
)


def _mark_missing_manifest_modules_uninstalled(env: Environment) -> None:
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
            "UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL, auto_install = FALSE WHERE name = %s",
            (module_name,),
        )


def _legacy_module_exists(env: Environment, module_name: str) -> bool:
    env.cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s LIMIT 1", (module_name,))
    return env.cr.fetchone() is not None


def _fetch_module_state(env: Environment, module_name: str) -> dict[str, object] | None:
    has_installed_version = openupgrade.column_exists(env.cr, "ir_module_module", "installed_version")
    column_names = ["state", "latest_version", "auto_install"]
    if has_installed_version:
        column_names.insert(2, "installed_version")
    query = f"SELECT {', '.join(column_names)} FROM ir_module_module WHERE name = %s"
    env.cr.execute(query, (module_name,))
    row = env.cr.fetchone()
    if not row:
        return None
    installed_version = row[2] if has_installed_version else None
    auto_install = row[3] if has_installed_version else row[2]
    return {
        "state": row[0],
        "latest_version": row[1],
        "installed_version": installed_version,
        "auto_install": auto_install,
    }


# noinspection DuplicatedCode
def _parse_manifest(manifest_path: Path) -> dict:
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_tree = ast.parse(manifest_text)
    for node in manifest_tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.Assign, ast.Expr)):
            return ast.literal_eval(node.value)
    raise ValueError(f"Manifest file {manifest_path} did not contain a dict literal")


def _collect_manifest_data_ids(module_name: str) -> set[str]:
    module_path = get_module_path(module_name)
    if not module_path:
        return set()
    manifest_path = Path(module_path) / "__manifest__.py"
    if not manifest_path.exists():
        return set()

    manifest = _parse_manifest(manifest_path)
    data_files = manifest.get("data", []) or []
    record_ids: set[str] = set()

    for relative_path in data_files:
        file_path = Path(module_path) / relative_path
        if not file_path.exists():
            continue
        if file_path.suffix == ".xml":
            record_ids.update(_collect_xml_ids(file_path))
        elif file_path.suffix == ".csv":
            record_ids.update(_collect_csv_ids(file_path))
    return record_ids


def _collect_xml_ids(xml_path: Path) -> set[str]:
    import xml.etree.ElementTree as ElementTree

    record_ids: set[str] = set()
    xml_tree = ElementTree.parse(xml_path)
    root = xml_tree.getroot()
    candidates: list[ElementTree.Element] = []

    for child in list(root):
        if child.tag == "data":
            candidates.extend(list(child))
        else:
            candidates.append(child)

    for element in candidates:
        record_id = element.get("id")
        if record_id:
            record_ids.add(record_id)
    return record_ids


def _collect_csv_ids(csv_path: Path) -> set[str]:
    record_ids: set[str] = set()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "id" not in fieldnames:
            return record_ids
        for row in reader:
            record_id = (row.get("id") or "").strip()
            if record_id:
                record_ids.add(record_id)
    return record_ids


def _reassign_xml_ids(env: Environment, target_module: str, xml_ids: set[str]) -> None:
    if not xml_ids:
        return
    env.cr.execute(
        "UPDATE ir_model_data SET module = %s WHERE module = %s AND name = ANY(%s)",
        (target_module, LEGACY_MODULE, list(xml_ids)),
    )


def _rename_legacy_module(env: Environment) -> None:
    env.cr.execute("UPDATE ir_module_module SET name = %s WHERE name = %s", (RENAMED_MODULE, LEGACY_MODULE))
    env.cr.execute(
        "UPDATE ir_module_module_dependency SET name = %s WHERE name = %s",
        (RENAMED_MODULE, LEGACY_MODULE),
    )
    env.cr.execute("UPDATE ir_model_data SET module = %s WHERE module = %s", (RENAMED_MODULE, LEGACY_MODULE))


def _rename_product_connect(env: Environment) -> None:
    if not _legacy_module_exists(env, LEGACY_MODULE):
        return

    legacy_state = _fetch_module_state(env, LEGACY_MODULE) or {}

    for module_name in MOVED_MODULES:
        record_ids = _collect_manifest_data_ids(module_name)
        _reassign_xml_ids(env, module_name, record_ids)

    if _legacy_module_exists(env, RENAMED_MODULE):
        renamed_state = _fetch_module_state(env, RENAMED_MODULE) or {}
        renamed_status = renamed_state.get("state")
        legacy_status = legacy_state.get("state")
        if renamed_status in {"uninstalled", "uninstallable"} and legacy_status not in {"uninstalled", "uninstallable"}:
            env.cr.execute(
                """
                UPDATE ir_module_module
                SET state = %s,
                    latest_version = COALESCE(%s, latest_version),
                    installed_version = COALESCE(%s, installed_version),
                    auto_install = COALESCE(%s, auto_install)
                WHERE name = %s
                """,
                (
                    legacy_state.get("state"),
                    legacy_state.get("latest_version"),
                    legacy_state.get("installed_version"),
                    legacy_state.get("auto_install"),
                    RENAMED_MODULE,
                ),
            )
        env.cr.execute(
            "UPDATE ir_module_module_dependency SET name = %s WHERE name = %s",
            (RENAMED_MODULE, LEGACY_MODULE),
        )
        env.cr.execute("UPDATE ir_model_data SET module = %s WHERE module = %s", (RENAMED_MODULE, LEGACY_MODULE))
        env.cr.execute("DELETE FROM ir_module_module WHERE name = %s", (LEGACY_MODULE,))
        return

    _rename_legacy_module(env)


def _clean_user_group_views(env: Environment) -> None:
    """Normalize legacy user group fields before the 19.0 view update."""

    candidate_xml_ids = ("user_groups_view", "view_users_form")

    def _fetch_view_id(xml_id_key: str) -> int | None:
        env.cr.execute(
            "SELECT res_id FROM ir_model_data WHERE module = 'base' AND name = %s AND model = 'ir.ui.view' LIMIT 1",
            (xml_id_key,),
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
        updated_text = re.sub(
            r"<label[^>]+for=\"user_group_warning\"[^>]*>\s*</label>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(
            r"<label[^>]+for='user_group_warning'[^>]*>\s*</label>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(r"<label[^>]+for=\"user_group_warning\"[^>]*/>", "", updated_text)
        updated_text = re.sub(r"<label[^>]+for='user_group_warning'[^>]*/>", "", updated_text)
        updated_text = re.sub(
            r"<label[^>]+for=\"(sel_groups_|in_group_)[^\"]+\"[^>]*>\s*</label>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(
            r"<label[^>]+for='(sel_groups_|in_group_)[^']+'[^>]*>\s*</label>",
            "",
            updated_text,
            flags=re.DOTALL,
        )
        updated_text = re.sub(
            r"<label[^>]+for=\"(sel_groups_|in_group_)[^\"]+\"[^>]*/>",
            "",
            updated_text,
        )
        updated_text = re.sub(r"<label[^>]+for='(sel_groups_|in_group_)[^']+'[^>]*/>", "", updated_text)
        updated_text = re.sub(r"\buser_group_warning\b", "False", updated_text)
        updated_text = re.sub(r"\bsel_groups_[0-9_]+\b", "False", updated_text)
        updated_text = re.sub(r"\bin_group_[0-9_]+\b", "False", updated_text)
        return updated_text

    for xml_id_name in candidate_xml_ids:
        view_id = _fetch_view_id(xml_id_name)
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


def _normalize_legacy_search_group_tags(env: Environment) -> None:
    """Normalize legacy search-view ``group`` tags for Odoo 19.

    Odoo 19 search views no longer accept attributes on ``group`` tags. Legacy
    noupdate views from 18.0 can still include attributes such as ``expand`` or
    ``string``, which makes XML validation fail during module loading.
    """

    def _normalize_view_text(view_text: str) -> str:
        if "search" not in view_text:
            return view_text
        return re.sub(r"<group\b[^>]*>", "<group>", view_text)

    env.cr.execute(
        "SELECT id, arch_db FROM ir_ui_view WHERE arch_db::text LIKE %s AND arch_db::text LIKE %s",
        ("%search%", "%<group %"),
    )
    candidate_rows = env.cr.fetchall()
    updated_view_count = 0

    for view_id, view_arch in candidate_rows:
        if isinstance(view_arch, dict):
            updated_payload = {locale: _normalize_view_text(text) for locale, text in view_arch.items()}
            if updated_payload == view_arch:
                continue
            env.cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(updated_payload), view_id))
            updated_view_count += 1
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
                updated_view_count += 1
                continue

        updated_arch = _normalize_view_text(str(view_arch))
        if updated_arch == str(view_arch):
            continue
        env.cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (updated_arch, view_id))
        updated_view_count += 1

    _logger.warning(
        "Normalized legacy search view group tags (candidates=%s, updated=%s)",
        len(candidate_rows),
        updated_view_count,
    )


def _normalize_legacy_inventory_valuation_values(env: Environment) -> None:
    """Map legacy valuation enum values removed in Odoo 19.

    Odoo 18 databases can contain the selection value ``manual_periodic``.
    Odoo 19 replaced it with ``manual``. Normalize persisted values before
    module graph loading to avoid selection validation errors while updating
    records during data imports.
    """

    def _normalize_selection_column_value(table_name: str, column_name: str, legacy_value: str, modern_value: str) -> int:
        if not openupgrade.column_exists(env.cr, table_name, column_name):
            return 0

        env.cr.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        metadata_row = env.cr.fetchone()
        data_type = metadata_row[0] if metadata_row else "text"

        quoted_legacy_value = json.dumps(legacy_value)
        if data_type == "jsonb":
            env.cr.execute(
                f"""
                UPDATE {table_name}
                SET {column_name} = to_jsonb(%s::text)
                WHERE {column_name}::text = %s
                """,
                (modern_value, quoted_legacy_value),
            )
            return env.cr.rowcount
        if data_type == "json":
            env.cr.execute(
                f"""
                UPDATE {table_name}
                SET {column_name} = to_json(%s::text)
                WHERE {column_name}::text = %s
                """,
                (modern_value, quoted_legacy_value),
            )
            return env.cr.rowcount

        env.cr.execute(
            f"UPDATE {table_name} SET {column_name} = %s WHERE {column_name} = %s",
            (modern_value, legacy_value),
        )
        return env.cr.rowcount

    updated_product_category_rows = _normalize_selection_column_value(
        table_name="product_category",
        column_name="property_valuation",
        legacy_value="manual_periodic",
        modern_value="manual",
    )

    updated_company_rows = _normalize_selection_column_value(
        table_name="res_company",
        column_name="inventory_valuation",
        legacy_value="manual_periodic",
        modern_value="manual",
    )

    updated_property_rows = 0
    if openupgrade.column_exists(env.cr, "ir_property", "value_text"):
        env.cr.execute(
            "UPDATE ir_property SET value_text = %s WHERE value_text = %s",
            ("manual", "manual_periodic"),
        )
        updated_property_rows = env.cr.rowcount

    _logger.warning(
        "Normalized legacy valuation values (product_category=%s, res_company=%s, ir_property=%s)",
        updated_product_category_rows,
        updated_company_rows,
        updated_property_rows,
    )


def _ensure_env(cursor_or_env: Cursor | Environment) -> Environment:
    if isinstance(cursor_or_env, api.Environment):
        return cursor_or_env
    return api.Environment(cursor_or_env, SUPERUSER_ID, {})


@openupgrade.migrate()
def migrate(cr: Cursor, version: str) -> None:
    """Pre-migration hook for base (19.0.1.0)."""
    _ = version
    env = _ensure_env(cr)
    _logger.warning("Running custom base pre-migration hook from openupgrade_scripts_custom")
    _mark_missing_manifest_modules_uninstalled(env)
    _rename_product_connect(env)
    _normalize_legacy_inventory_valuation_values(env)
    _normalize_legacy_search_group_tags(env)
    _clean_user_group_views(env)
