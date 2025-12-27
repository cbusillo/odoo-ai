from odoo import api, fields, models


class RepairOrder(models.Model):
    _inherit = "repair.order"

    motor = fields.Many2one("motor", related="product_id.motor", store=True, index=True, readonly=True, ondelete="restrict")
    motor_number = fields.Char(related="motor.motor_number", store=True, readonly=True, index=True)
    product_list_price = fields.Float(related="product_id.product_tmpl_id.list_price", readonly=False, string="Product Price")
    product_standard_price = fields.Float(related="product_id.product_tmpl_id.standard_price", string="Product Cost")
    repair_cost = fields.Float(compute="_compute_total_estimated_cost", store=True)

    @api.depends("move_ids.quantity", "move_ids.product_id.product_tmpl_id.standard_price")
    def _compute_total_estimated_cost(self) -> None:
        for order in self:
            order.repair_cost = sum(m.product_id.product_tmpl_id.standard_price * m.product_uom_qty for m in order.move_ids)

    def action_repair_done(self) -> "odoo.values.repair_order":
        res = super().action_repair_done()
        for order in self:
            for _move in order.move_ids:  # TODO: Add code to decrement product quantity from Shopify
                pass
            product = order.product_id.product_tmpl_id
            cost = sum(m.product_tmpl_id.standard_price * m.quantity for m in order.move_ids)
            quantity = product.qty_available if product.is_ready_for_sale else product.initial_quantity
            cost_per_unit = cost / quantity if quantity else 0.0
            product.standard_price += cost_per_unit
        return res
