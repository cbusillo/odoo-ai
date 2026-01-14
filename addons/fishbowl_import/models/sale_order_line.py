from odoo import models


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["sale.order.line", "external.id.mixin"]
    _description = "Sales Order Line"
