# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from typing import Any

from odoo import SUPERUSER_ID, api
from openupgradelib import openupgrade


def _trim_record_translations_for_odoo_19(
    env: Any,
    module: str,
    xml_ids: list[str] | tuple[str, ...],
    field_names: list[str],
) -> None:
    """Drop non-en_US JSONB translations for selected XML records.

    Odoo 19 stores ``ir_model_fields.translate`` as a string (for example,
    ``standard``/``html_translate``), while openupgradelib still treats it as a
    boolean in ``delete_record_translations``. This local helper keeps the
    intended behavior without relying on the old boolean predicate.
    """

    if not xml_ids:
        return

    env.cr.execute(
        """
        SELECT model, res_id
        FROM ir_model_data
        WHERE module = %s AND name IN %s
        """,
        (module, tuple(xml_ids)),
    )

    for model_name, record_id in env.cr.fetchall():
        table_name = openupgrade.get_model2table(model_name)
        env.cr.execute(
            """
            SELECT information_schema.columns.column_name
            FROM information_schema.columns
            JOIN ir_model_fields
              ON ir_model_fields.name = information_schema.columns.column_name
             AND ir_model_fields.model = %s
            WHERE information_schema.columns.table_name = %s
              AND COALESCE(ir_model_fields.translate, '') <> ''
            """,
            (model_name, table_name),
        )
        translated_columns = [column_name for (column_name,) in env.cr.fetchall()]
        translated_columns = [
            column_name for column_name in translated_columns if column_name in field_names
        ]
        if not translated_columns:
            continue

        condition_checks = ", ".join(
            (
                f"{column_name} IS NOT NULL"
                f" AND ({column_name} ? 'en_US')"
                f" AND (SELECT count(*) FROM jsonb_object_keys({column_name})) > 1"
            )
            for column_name in translated_columns
        )
        env.cr.execute(
            f"SELECT {condition_checks} FROM {table_name} WHERE id = %s", (record_id,)
        )
        condition_result = env.cr.fetchone()
        if not condition_result:
            continue

        columns_to_trim = [
            column_name
            for column_name, should_trim in zip(translated_columns, condition_result)
            if should_trim
        ]
        if not columns_to_trim:
            continue

        target_columns = ", ".join(columns_to_trim)
        target_values = ", ".join(
            f"jsonb_build_object('en_US', {column_name} -> 'en_US')"
            for column_name in columns_to_trim
        )
        if len(columns_to_trim) > 1:
            target_columns = f"({target_columns})"
            target_values = f"({target_values})"

        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE {table_name}
               SET {target_columns} = {target_values}
             WHERE id = %s
            """,
            (record_id,),
        )


def _install_translate_aware_delete_record_translations_patch() -> None:
    if getattr(openupgrade, "_sc_translate_patch_installed", False):
        return

    original_delete_record_translations = openupgrade.delete_record_translations

    def patched_delete_record_translations(
        cursor: Any,
        module: str,
        xml_ids: list[str] | tuple[str, ...],
        field_list: list[str] | None = None,
    ) -> None:
        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'ir_model_fields' AND column_name = 'translate'
            """
        )
        translate_type_row = cursor.fetchone()
        if translate_type_row and translate_type_row[0] in {"character varying", "text"}:
            environment = api.Environment(cursor, SUPERUSER_ID, {})
            _trim_record_translations_for_odoo_19(
                environment,
                module=module,
                xml_ids=xml_ids,
                field_names=field_list or [],
            )
        else:
            original_delete_record_translations(cursor, module, xml_ids, field_list)

    openupgrade.delete_record_translations = patched_delete_record_translations
    openupgrade._sc_translate_patch_installed = True


@openupgrade.migrate()
def migrate(env, version) -> None:
    _ = version
    _install_translate_aware_delete_record_translations_patch()
    openupgrade.load_data(env, "auth_signup", "19.0.1.0/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "auth_signup",
        ["mail_template_user_signup_account_created", "set_password_email"],
        ["body_html"],
    )
