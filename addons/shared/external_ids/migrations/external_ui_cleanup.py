from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

OBSOLETE_EXTERNAL_ID_VIEW_XMLIDS = (
    "view_employee_form_external_ids",
    "view_partner_form_external_ids",
    "view_product_template_form_external_ids",
)


def _find_obsolete_view_ids(cr: Cursor) -> list[int]:
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
    return [view_id for (view_id,) in cr.fetchall()]


def deactivate_obsolete_external_id_views(cr: Cursor) -> list[int]:
    view_ids = _find_obsolete_view_ids(cr)
    if not view_ids:
        return []
    cr.execute("UPDATE ir_ui_view SET active = FALSE WHERE id = ANY(%s)", (view_ids,))
    return view_ids


def unlink_obsolete_external_id_views(cr: Cursor) -> list[int]:
    view_ids = _find_obsolete_view_ids(cr)
    if not view_ids:
        return []

    env = api.Environment(cr, SUPERUSER_ID, {})
    view_model = env["ir.ui.view"].sudo().with_context(active_test=False)
    view_records = view_model.browse(view_ids).exists()
    if view_records:
        view_records.unlink()

    env["ir.model.data"].sudo().search(
        [
            ("module", "=", "external_ids"),
            ("model", "=", "ir.ui.view"),
            ("name", "in", list(OBSOLETE_EXTERNAL_ID_VIEW_XMLIDS)),
        ]
    ).unlink()
    return view_ids
