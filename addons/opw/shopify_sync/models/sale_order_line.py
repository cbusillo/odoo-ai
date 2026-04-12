from odoo import models

from .external_references import SHOPIFY_ORDER_LINE_BINDING


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["sale.order.line", "external.id.mixin"]
    _description = "Sales Order Line"
    _external_id_binding = SHOPIFY_ORDER_LINE_BINDING
