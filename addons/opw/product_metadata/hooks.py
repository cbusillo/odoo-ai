from odoo import SUPERUSER_ID, api


def pre_init_hook(env_or_cursor) -> None:
    cursor = env_or_cursor.cr if isinstance(env_or_cursor, api.Environment) else env_or_cursor
    _ensure_condition_xmlids(cursor)


def _ensure_condition_xmlids(cursor) -> None:
    cursor.execute("SELECT to_regclass('product_condition')")
    table_name = cursor.fetchone()
    if not table_name or table_name[0] is None:
        return

    mappings = [
        ("product_condition_used", "used", "Used"),
        ("product_condition_new", "new", "New"),
        ("product_condition_open_box", "open_box", "Open Box"),
        ("product_condition_broken", "broken", "Broken"),
        ("product_condition_refurbished", "refurbished", "Refurbished"),
    ]

    for xml_id, code, name in mappings:
        cursor.execute(
            """
            SELECT 1
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
             LIMIT 1
            """,
            ("product_metadata", xml_id),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            SELECT id, code
              FROM product_condition
             WHERE code = %s
             LIMIT 1
            """,
            (code,),
        )
        condition = cursor.fetchone()
        if not condition:
            cursor.execute(
                """
                SELECT id, code
                  FROM product_condition
                 WHERE name = %s
                 LIMIT 1
                """,
                (name,),
            )
            condition = cursor.fetchone()
        if not condition:
            continue

        condition_id, existing_code = condition
        if existing_code != code:
            cursor.execute(
                """
                UPDATE product_condition
                   SET code = %s
                 WHERE id = %s
                """,
                (code, condition_id),
            )

        cursor.execute(
            """
            INSERT INTO ir_model_data
                (module, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s, %s, true, %s, NOW(), %s, NOW())
            """,
            ("product_metadata", xml_id, "product.condition", condition_id, SUPERUSER_ID, SUPERUSER_ID),
        )
