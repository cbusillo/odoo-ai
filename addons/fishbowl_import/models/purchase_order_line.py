from odoo import models


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["purchase.order.line", "external.id.mixin"]
    _description = "Purchase Order Line"
