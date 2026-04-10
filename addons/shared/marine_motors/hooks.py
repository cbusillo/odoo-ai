import json

from odoo import SUPERUSER_ID, api
from odoo.orm.environments import Environment
from odoo.sql_db import Cursor

MARINE_MOTORS_SNAPSHOT_PARAMETER = "marine_motors.migration.split_preserved_state"


def pre_init_hook(env_or_cursor: Environment | Cursor) -> None:
    cursor = env_or_cursor.cr if isinstance(env_or_cursor, api.Environment) else env_or_cursor
    _ensure_motor_test_selection_xmlids(cursor)


def post_init_hook(env_or_cursor: Environment | Cursor, registry: object | None = None) -> None:
    if isinstance(env_or_cursor, api.Environment):
        env = env_or_cursor
    else:
        env = api.Environment(env_or_cursor, SUPERUSER_ID, {})
    _restore_marine_motors_split_state(env)


def _restore_marine_motors_split_state(env: api.Environment) -> None:
    config_parameter_model = env["ir.config_parameter"].sudo()
    snapshot_record = config_parameter_model.search(
        [("key", "=", MARINE_MOTORS_SNAPSHOT_PARAMETER)],
        limit=1,
    )
    if not snapshot_record:
        return

    try:
        snapshot_payload = json.loads(snapshot_record.value)
    except (json.JSONDecodeError, TypeError):
        snapshot_record.unlink()
        return

    _restore_many_to_many_xmlids(
        env,
        model_name="motor.test.template",
        field_name="selection_options",
        xmlids_by_owner=snapshot_payload.get("selection_options", {}),
    )
    _restore_many_to_many_xmlids(
        env,
        model_name="motor.part.template",
        field_name="hidden_tests",
        xmlids_by_owner=snapshot_payload.get("hidden_tests", {}),
    )
    _restore_scalar_values(
        env,
        model_name="motor.test.section",
        field_name="sequence",
        values_by_xmlid=snapshot_payload.get("section_sequences", {}),
    )
    _restore_scalar_values(
        env,
        model_name="motor.part.template",
        field_name="name",
        values_by_xmlid=snapshot_payload.get("part_names", {}),
    )
    snapshot_record.unlink()


def _restore_many_to_many_xmlids(
    env: api.Environment,
    *,
    model_name: str,
    field_name: str,
    xmlids_by_owner: dict[str, list[str]],
) -> None:
    if not xmlids_by_owner:
        return

    model = env[model_name].sudo()
    for owner_xmlid, related_xmlids in xmlids_by_owner.items():
        owner_record = env.ref(f"marine_motors.{owner_xmlid}", raise_if_not_found=False)
        owner_record = owner_record.exists() if owner_record else model.browse()
        if not owner_record:
            continue

        related_model_name = owner_record._fields[field_name].comodel_name
        related_model = env[related_model_name].sudo()

        related_record_ids: list[int] = []
        for related_xmlid in related_xmlids:
            related_record = env.ref(f"marine_motors.{related_xmlid}", raise_if_not_found=False)
            related_record = related_record.exists() if related_record else related_model.browse()
            if related_record:
                related_record_ids.append(related_record.id)

        owner_record.write({field_name: [(6, 0, related_record_ids)]})


def _restore_scalar_values(
    env: api.Environment,
    *,
    model_name: str,
    field_name: str,
    values_by_xmlid: dict[str, object],
) -> None:
    if not values_by_xmlid:
        return

    model = env[model_name].sudo()
    for owner_xmlid, value in values_by_xmlid.items():
        owner_record = env.ref(f"marine_motors.{owner_xmlid}", raise_if_not_found=False)
        owner_record = owner_record.exists() if owner_record else model.browse()
        if owner_record:
            owner_record.write({field_name: value})


def _ensure_motor_test_selection_xmlids(cursor: Cursor) -> None:
    cursor.execute("SELECT to_regclass('motor_test_selection')")
    table_name = cursor.fetchone()
    if not table_name or table_name[0] is None:
        return

    mappings = [
        ("option_shaft_length_15", "15", '15" Short Shaft'),
        ("option_shaft_length_20", "20", '20" Long Shaft'),
        ("option_shaft_length_25", "25", '25" XL Shaft'),
        ("option_shaft_length_30", "30", '30" XXL Shaft'),
        ("option_not_tested", "not_tested", "Not Tested"),
        ("option_locked", "locked", "Locked up"),
        ("option_rotation_counter", "counter", "Counter Rotation"),
        ("option_rotation_standard", "standard", "Standard Rotation"),
        ("option_functional", "functional", "Functional"),
        ("option_non_functional", "non_functional", "Non-Functional"),
        ("option_no_issues", "no_issues", "No Issues"),
        ("option_bad_motor", "bad_motor", "Bad Motor"),
        ("option_needs_attention", "needs_attention", "Needs Attention"),
        ("option_manual", "manual", "Manual"),
    ]

    for xml_id, value, name in mappings:
        cursor.execute(
            """
            SELECT 1
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
             LIMIT 1
            """,
            ("marine_motors", xml_id),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            SELECT id, value
              FROM motor_test_selection
             WHERE value = %s
             LIMIT 1
            """,
            (value,),
        )
        selection = cursor.fetchone()
        if not selection:
            cursor.execute(
                """
                SELECT id, value
                  FROM motor_test_selection
                 WHERE name = %s
                 LIMIT 1
                """,
                (name,),
            )
            selection = cursor.fetchone()
        if not selection:
            continue

        selection_id, existing_value = selection
        if existing_value != value:
            cursor.execute(
                """
                UPDATE motor_test_selection
                   SET value = %s
                 WHERE id = %s
                """,
                (value, selection_id),
            )

        cursor.execute(
            """
            INSERT INTO ir_model_data
                (module, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s, %s, true, %s, NOW(), %s, NOW())
            """,
            ("marine_motors", xml_id, "motor.test.selection", selection_id, SUPERUSER_ID, SUPERUSER_ID),
        )
