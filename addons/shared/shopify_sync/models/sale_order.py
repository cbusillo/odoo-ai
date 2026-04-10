from odoo import api, fields, models

from .external_references import SHOPIFY_ORDER_BINDING


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "external.id.mixin"]
    _description = "Sales Order"
    _external_id_binding = SHOPIFY_ORDER_BINDING

    shopify_note = fields.Text(
        string="Shopify Note",
        help="Imported notes from Shopify/eBay (payment info, order notes, eBay details). The standard note field is reserved for manual Odoo notes.",
    )

    source_platform = fields.Selection([("shopify", "Shopify"), ("ebay", "eBay"), ("manual", "Manual")], string="Source Platform")

    shipping_charge = fields.Monetary(string="Shipping Charged to Customer")
    shipping_paid = fields.Monetary(string="Shipping Paid to Carrier")
    shipping_margin = fields.Monetary(string="Shipping Margin", compute="_compute_shipping_margin", store=True)

    shipping_tracking_numbers = fields.Text(string="Tracking Numbers")

    @api.depends("shipping_charge", "shipping_paid")
    def _compute_shipping_margin(self) -> None:
        for order in self:
            order.shipping_margin = order.shipping_charge - order.shipping_paid
