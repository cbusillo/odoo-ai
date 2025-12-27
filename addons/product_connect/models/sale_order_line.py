from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    shopify_order_line_id = fields.Char(string="Shopify Order Line ID", copy=False)
