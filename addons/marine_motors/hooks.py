from odoo import SUPERUSER_ID, api


def pre_init_hook(env_or_cursor) -> None:
    cursor = env_or_cursor.cr if isinstance(env_or_cursor, api.Environment) else env_or_cursor
    _ensure_motor_test_selection_xmlids(cursor)


def _ensure_motor_test_selection_xmlids(cursor) -> None:
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
