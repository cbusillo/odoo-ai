from odoo import SUPERUSER_ID, api

from odoo.addons.fishbowl_import.hooks import _schedule_fishbowl_import


def _remove_legacy_external_id_views(env: "api.Environment") -> None:
    legacy_view_names = {
        "view_sale_order_form_external_ids",
        "view_purchase_order_form_external_ids",
        "view_stock_picking_form_external_ids",
    }
    model_data = (
        env["ir.model.data"]
        .sudo()
        .search(
            [
                ("module", "=", "external_ids"),
                ("model", "=", "ir.ui.view"),
                ("name", "in", list(legacy_view_names)),
            ]
        )
    )
    for record in model_data:
        view = env["ir.ui.view"].sudo().browse(record.res_id)
        if view.exists():
            view.unlink()
        record.unlink()


def migrate(cr, _version) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    _remove_legacy_external_id_views(env)
    _schedule_fishbowl_import(env, reason="post_upgrade")
