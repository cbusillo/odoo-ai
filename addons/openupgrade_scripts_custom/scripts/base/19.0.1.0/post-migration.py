# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.modules.module import get_module_path
from odoo.orm.environments import Environment
from openupgradelib import openupgrade


def _cleanup_web_editor_metadata(env: Environment) -> None:
    """Drop dangling `web_editor.*` model metadata.

    The restored 18.0 database can contain `ir_model*` rows for `web_editor.*`
    even when the module is missing from the 19.0 addons paths.

    Removing the model metadata avoids registry warnings during the upgrade.
    """

    # Only perform this cleanup when the addon is actually absent from the
    # addons path. Some environments legitimately have `web_editor` available
    # (enterprise), and deleting its metadata would be destructive.
    if get_module_path("web_editor"):
        return

    env.cr.execute("SELECT id FROM ir_module_module WHERE name = 'web_editor' LIMIT 1")
    module_row = env.cr.fetchone()
    if module_row:
        env.cr.execute(
            "UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL WHERE id = %s",
            (module_row[0],),
        )

    env.cr.execute("SELECT id, model FROM ir_model WHERE model LIKE 'web_editor.%' ORDER BY model")
    model_rows = env.cr.fetchall()
    if not model_rows:
        return

    model_ids = [row[0] for row in model_rows]
    model_names = [row[1] for row in model_rows]

    env.cr.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND table_name = 'ir_model_constraint' "
        "  AND column_name = 'model'",
    )
    constraint_model_type_row = env.cr.fetchone()
    constraint_model_is_integer = not constraint_model_type_row or constraint_model_type_row[0] in ("integer", "bigint")

    env.cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND res_id IN "
        "(SELECT id FROM ir_model_fields WHERE model = ANY(%s))",
        (model_names,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'ir.model.access' AND res_id IN "
        "(SELECT id FROM ir_model_access WHERE model_id = ANY(%s))",
        (model_ids,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'ir.model' AND res_id = ANY(%s)",
        (model_ids,),
    )

    env.cr.execute(
        "DELETE FROM ir_model_fields_selection WHERE field_id IN (SELECT id FROM ir_model_fields WHERE model = ANY(%s))",
        (model_names,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_fields WHERE model = ANY(%s)",
        (model_names,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_access WHERE model_id = ANY(%s)",
        (model_ids,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_constraint WHERE model = ANY(%s)",
        (model_ids if constraint_model_is_integer else model_names,),
    )
    env.cr.execute(
        "DELETE FROM ir_model_inherit WHERE model_id = ANY(%s) OR parent_id = ANY(%s)",
        (model_ids, model_ids),
    )
    env.cr.execute("DELETE FROM ir_model WHERE id = ANY(%s)", (model_ids,))


def _fix_ir_rule_user_groups_field(env: Environment) -> None:
    """Fix legacy ir.rule domains referencing `user.groups_id`.

    In Odoo 19, the `res.users` field is `group_ids`. Some restored databases
    can contain rules that still use `user.groups_id` in `domain_force`, which
    causes 500s during record rule evaluation.
    """

    users_fields = env["res.users"]._fields
    has_group_ids = "group_ids" in users_fields
    has_groups_id = "groups_id" in users_fields
    if has_group_ids and not has_groups_id:
        env.cr.execute(
            "UPDATE ir_rule "
            "SET domain_force = replace(domain_force, 'user.groups_id', 'user.group_ids') "
            "WHERE domain_force LIKE '%user.groups_id%';",
        )
        return
    if has_groups_id and not has_group_ids:
        env.cr.execute(
            "UPDATE ir_rule "
            "SET domain_force = replace(domain_force, 'user.group_ids', 'user.groups_id') "
            "WHERE domain_force LIKE '%user.group_ids%';",
        )
        return


def _fix_user_groups_view_field(env: Environment) -> None:
    """Align base.user_groups_view with the Odoo 19 `group_ids` field."""

    view_record = env.ref("base.user_groups_view", raise_if_not_found=False)
    if not view_record:
        return
    view_arch = view_record.arch_db or ""
    if 'name="groups_id"' not in view_arch:
        return
    updated_arch = view_arch.replace('name="groups_id"', 'name="group_ids"')
    if updated_arch == view_arch:
        return
    view_record.write({"arch_db": updated_arch})


@openupgrade.migrate()
def migrate(env: Environment, _version: str) -> None:
    """Post-migration hook for base (19.0.1.0)."""

    _fix_ir_rule_user_groups_field(env)
    _fix_user_groups_view_field(env)
    _cleanup_web_editor_metadata(env)
