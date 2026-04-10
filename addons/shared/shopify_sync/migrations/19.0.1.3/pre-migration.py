from odoo.sql_db import Cursor


OBSOLETE_EXTERNAL_ID_VIEW_XMLIDS = (
    "view_employee_form_external_ids",
    "view_partner_form_external_ids",
    "view_product_template_form_external_ids",
)


def migrate(cr: Cursor, version: str) -> None:
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = %s
           AND model = %s
           AND name = ANY(%s)
        """,
        ("external_ids", "ir.ui.view", list(OBSOLETE_EXTERNAL_ID_VIEW_XMLIDS)),
    )
    view_ids = [view_id for (view_id,) in cr.fetchall()]
    if view_ids:
        cr.execute("UPDATE ir_ui_view SET active = FALSE WHERE id = ANY(%s)", (view_ids,))
