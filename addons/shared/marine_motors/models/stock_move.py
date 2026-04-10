from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    line_cost = fields.Float(compute="_compute_line_cost_price", store=True)
    line_price = fields.Float(compute="_compute_line_cost_price", store=True)

    @api.depends(
        "product_id",
        "quantity",
        "product_id.product_tmpl_id.standard_price",
        "product_id.product_tmpl_id.list_price",
    )
    def _compute_line_cost_price(self) -> None:
        for move in self:
            if not move.product_id:
                move.line_cost = 0.0
                move.line_price = 0.0
                continue
            move.line_cost = move.product_id.product_tmpl_id.standard_price * move.quantity
            move.line_price = move.product_id.product_tmpl_id.list_price * move.quantity
