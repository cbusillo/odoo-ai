from odoo import api, fields, models

from ..services.shopify.helpers import SyncMode


class ProductTemplate(models.Model):
    _inherit = "product.template"

    shopify_product_url = fields.Char(
        compute="_compute_shopify_urls",
        string="Shopify Product Link",
    )
    shopify_product_admin_url = fields.Char(
        compute="_compute_shopify_urls",
        string="Shopify Product Admin Link",
    )

    def _post_create_actions(self) -> None:
        if self.env.context.get("skip_shopify_sync"):
            return

        consumable_products = self.filtered(lambda p: p.type == "consu" and p.is_ready_for_sale and p.is_published)
        if not consumable_products:
            return

        variant_ids = consumable_products.mapped("product_variant_ids").ids
        self.env["shopify.sync"].create_and_run_async(
            {"mode": SyncMode.EXPORT_BATCH_PRODUCTS, "odoo_products_to_sync": [(6, 0, variant_ids)]}
        )

    def _post_write_actions(self) -> None:
        if self.env.context.get("skip_shopify_sync"):
            return

        variant_ids = self.filtered(lambda p: p.type == "consu" and p.is_ready_for_sale and p.is_published)
        if not variant_ids:
            return

        commands = [(4, variant_id) for variant_id in variant_ids.mapped("product_variant_ids").ids]
        self.env["shopify.sync"].create_and_run_async({"mode": SyncMode.EXPORT_BATCH_PRODUCTS, "odoo_products_to_sync": commands})

    @api.depends(
        "product_variant_ids.external_ids.external_id",
        "product_variant_ids.external_ids.system_id",
        "product_variant_ids.external_ids.resource",
        "product_variant_ids.external_ids.active",
    )
    def _compute_shopify_urls(self) -> None:
        for template in self:
            variant = template.product_variant_id
            if not variant:
                template.shopify_product_admin_url = False
                template.shopify_product_url = False
                continue

            template.shopify_product_admin_url = variant.get_external_url(
                "shopify",
                kind="product_admin",
                resource="product",
            )
            template.shopify_product_url = variant.get_external_url(
                "shopify",
                kind="product_store",
                resource="product",
            )
