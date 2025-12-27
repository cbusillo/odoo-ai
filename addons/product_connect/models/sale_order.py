from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    shopify_order_id = fields.Char(string="Shopify Order ID", copy=False)
    shopify_note = fields.Text(
        string="Shopify Note",
        help="Imported notes from Shopify/eBay (payment info, order notes, eBay details). The standard note field is reserved for manual Odoo notes.",
    )

    ebay_order_id = fields.Char(string="eBay Order ID", copy=False)
    source_platform = fields.Selection([("shopify", "Shopify"), ("ebay", "eBay"), ("manual", "Manual")], string="Source Platform")

    shipping_charge = fields.Monetary(string="Shipping Charged to Customer")
    shipping_paid = fields.Monetary(string="Shipping Paid to Carrier")
    shipping_margin = fields.Monetary(string="Shipping Margin", compute="_compute_shipping_margin", store=True)

    shipstation_order_id = fields.Char(string="ShipStation Order ID", copy=False)
    shipping_tracking_numbers = fields.Text(string="Tracking Numbers")

    @api.depends("shipping_charge", "shipping_paid")
    def _compute_shipping_margin(self) -> None:
        for order in self:
            order.shipping_margin = order.shipping_charge - order.shipping_paid
