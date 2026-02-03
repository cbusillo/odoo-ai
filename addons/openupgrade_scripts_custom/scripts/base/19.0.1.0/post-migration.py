import logging
from datetime import date

from odoo import SUPERUSER_ID, api
from odoo.api import Environment
from odoo.modules.module import get_module_path
from odoo.sql_db import Cursor
from openupgradelib import openupgrade

logger = logging.getLogger(__name__)


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
    """Align res.users views with the Odoo 19 `group_ids` field."""

    views = env["ir.ui.view"].search(
        [
            ("model", "=", "res.users"),
            ("arch_db", "ilike", 'name="groups_id"'),
        ]
    )
    for view_record in views:
        view_arch = view_record.arch_db or ""
        if 'name="groups_id"' not in view_arch:
            continue
        updated_arch = view_arch.replace('name="groups_id"', 'name="group_ids"')
        if updated_arch != view_arch:
            view_record.write({"arch_db": updated_arch})


def _ensure_env(cursor_or_env: Cursor | Environment) -> Environment:
    if isinstance(cursor_or_env, api.Environment):
        return cursor_or_env
    return api.Environment(cursor_or_env, SUPERUSER_ID, {})


def _ensure_not_null_constraint(env: Environment, table_name: str, column_name: str) -> None:
    env.cr.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table_name, column_name),
    )
    row = env.cr.fetchone()
    if not row or row[0] != "YES":
        return

    env.cr.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL",
    )
    null_count = env.cr.fetchone()[0]
    if null_count:
        logger.warning(
            "Skipping NOT NULL constraint for %s.%s; %s NULL rows remain.",
            table_name,
            column_name,
            null_count,
        )
        return

    env.cr.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL",
    )


def _enforce_required_picking_policy_constraints(env: Environment) -> None:
    _ensure_not_null_constraint(env, "res_config_settings", "default_picking_policy")
    _ensure_not_null_constraint(env, "sale_order", "picking_policy")


def _make_product_image_attachments_public(env: Environment) -> None:
    env.cr.execute(
        "SELECT COUNT(*) FROM ir_attachment "
        "WHERE res_model = 'product.image' "
        "  AND res_field = 'image_1920' "
        "  AND (public IS DISTINCT FROM TRUE)",
    )
    pending_count = env.cr.fetchone()[0]
    if not pending_count:
        return

    env.cr.execute(
        "UPDATE ir_attachment "
        "SET public = TRUE "
        "WHERE res_model = 'product.image' "
        "  AND res_field = 'image_1920' "
        "  AND (public IS DISTINCT FROM TRUE)",
    )
    logger.info("Marked %s product image attachments as public for Shopify exports.", pending_count)


def _table_exists(env: Environment, table_name: str) -> bool:
    env.cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    )
    return env.cr.fetchone() is not None


def _backfill_ready_for_sale_enabled_date(env: Environment) -> None:
    if not openupgrade.column_exists(env.cr, "product_template", "is_ready_for_sale_last_enabled_date"):
        return
    if not _table_exists(env, "product_template"):
        return

    noisy_dates = {date(2024, 2, 1), date(2024, 2, 2)}
    logger.info("Backfilling ready-for-sale enabled dates using SQL.")

    has_tracking_tables = all(
        _table_exists(env, table_name)
        for table_name in ("mail_message", "mail_tracking_value", "ir_model_fields")
    )
    if has_tracking_tables:
        env.cr.execute(
            """
            WITH tracking AS (
                SELECT mm.res_id AS product_id,
                       MAX(mm.create_date) AS enabled_at
                  FROM mail_message mm
                  JOIN mail_tracking_value mtv ON mtv.mail_message_id = mm.id
                  JOIN ir_model_fields field ON field.id = mtv.field_id
                 WHERE mm.model = 'product.template'
                   AND field.name = 'is_ready_for_sale'
                   AND mtv.new_value_integer = 1
                 GROUP BY mm.res_id
            )
            UPDATE product_template pt
               SET is_ready_for_sale_last_enabled_date = tracking.enabled_at
              FROM tracking
             WHERE pt.id = tracking.product_id
               AND pt.is_ready_for_sale = TRUE
               AND pt.is_ready_for_sale_last_enabled_date IS NULL
            """,
        )

    env.cr.execute(
        """
        UPDATE product_template
           SET is_ready_for_sale_last_enabled_date = create_date
         WHERE is_ready_for_sale = TRUE
           AND is_ready_for_sale_last_enabled_date IS NULL
           AND (create_date IS NULL OR create_date::date NOT IN (%s, %s))
        """,
        tuple(noisy_dates),
    )


def _fix_partner_data_issues(env: Environment) -> None:
    if not openupgrade.column_exists(env.cr, "res_partner", "autopost_bills"):
        return

    env.cr.execute("SELECT COUNT(*) FROM res_partner WHERE autopost_bills IS NULL")
    null_count_before = env.cr.fetchone()[0]
    if null_count_before:
        logger.info("Found %s partners with NULL autopost_bills", null_count_before)
        env.cr.execute("UPDATE res_partner SET autopost_bills = 'ask' WHERE autopost_bills IS NULL")

    env.cr.execute(
        "UPDATE res_partner SET name = phone WHERE name = '' AND type = 'contact' AND phone IS NOT NULL"
    )
    contact_fixed = env.cr.rowcount
    if contact_fixed:
        logger.info("Fixed %s contacts by using phone as name", contact_fixed)

    env.cr.execute("UPDATE res_partner SET name = 'Customer ' || id::text WHERE name = '' AND type = 'contact'")
    contact_placeholder = env.cr.rowcount
    if contact_placeholder:
        logger.info("Fixed %s contacts with placeholder names", contact_placeholder)

    env.cr.execute("UPDATE res_partner SET name = NULL WHERE name = '' AND type IN ('delivery', 'invoice')")
    address_fixed = env.cr.rowcount
    if address_fixed:
        logger.info("Fixed %s delivery/invoice partners by setting name NULL", address_fixed)


@openupgrade.migrate()
def migrate(cr: Cursor, version: str) -> None:
    """Post-migration hook for base (19.0.1.0)."""
    _ = version
    env = _ensure_env(cr)
    _fix_ir_rule_user_groups_field(env)
    _fix_user_groups_view_field(env)
    _cleanup_web_editor_metadata(env)
    _enforce_required_picking_policy_constraints(env)
    _make_product_image_attachments_public(env)
    _backfill_ready_for_sale_enabled_date(env)
    _fix_partner_data_issues(env)
