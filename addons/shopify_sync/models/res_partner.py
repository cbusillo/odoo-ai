from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"
    shopify_customer_admin_url = fields.Char(
        string="Shopify Customer Admin Link",
        compute="_compute_marketplace_urls",
    )
    ebay_profile_url = fields.Char(
        string="eBay Profile Link",
        compute="_compute_marketplace_urls",
    )

    @api.depends(
        "external_ids.external_id",
        "external_ids.system_id",
        "external_ids.resource",
        "external_ids.active",
    )
    def _compute_marketplace_urls(self) -> None:
        for partner in self:
            partner.shopify_customer_admin_url = partner.get_external_url(
                "shopify",
                kind="customer_admin",
                resource="customer",
            )
            partner.ebay_profile_url = partner.get_external_url(
                "ebay",
                kind="profile",
                resource="profile",
            )
