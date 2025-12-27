from odoo import api, fields, models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"
    _description = "Partner"

    ebay_username = fields.Char(string="eBay Username", copy=False)
    shopify_customer_id = fields.Char(string="Shopify Customer ID", copy=False)
    shopify_customer_admin_url = fields.Char(string="Shopify Customer Admin Link", compute="_compute_shopify_urls", store=True)
    shopify_address_id = fields.Char(string="Shopify Address ID", copy=False)
    ebay_profile_url = fields.Char(string="eBay Profile Link", compute="_compute_ebay_profile_url", store=True)

    @api.depends("shopify_customer_id")
    def _compute_shopify_urls(self) -> None:
        for partner in self:
            if partner.shopify_customer_id:
                shop_url_key = self.env["ir.config_parameter"].sudo().get_param("shopify.shop_url_key")
                partner.shopify_customer_admin_url = (
                    f"https://admin.shopify.com/store/{shop_url_key}/customers/{partner.shopify_customer_id}"
                )
            else:
                partner.shopify_customer_admin_url = False

    @api.depends("ebay_username")
    def _compute_ebay_profile_url(self) -> None:
        for partner in self:
            partner.ebay_profile_url = f"https://www.ebay.com/usr/{partner.ebay_username}" if partner.ebay_username else False
