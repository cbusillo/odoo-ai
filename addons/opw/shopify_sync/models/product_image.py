from odoo import api, models

from ..services.shopify.helpers import SyncMode


class ProductImage(models.Model):
    _name = "product.image"
    _inherit = ["product.image", "external.id.mixin"]

    def _mark_for_shopify_product_export(self) -> None:
        products_to_mark: "odoo.model.product_product" = self.env["product.product"]
        products_to_mark |= self.mapped("product_variant_id")
        templates = self.mapped("product_tmpl_id")
        if templates:
            products_to_mark |= templates.mapped("product_variant_ids")
        if not products_to_mark:
            return

        products_to_mark.write({"shopify_next_export": True})

        if not self.env.context.get("skip_immediate_sync"):
            self.env["shopify.sync"].create_and_run_async({"mode": SyncMode.EXPORT_CHANGED_PRODUCTS})

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.product_image"]) -> "odoo.model.product_image":
        records = super().create(vals_list)
        if not records.env.context.get("skip_shopify_sync"):
            records._mark_for_shopify_product_export()
        return records

    def write(self, vals: "odoo.values.product_image") -> bool:
        res = super().write(vals)
        if {"image_1920", "sequence"} & vals.keys() and not self.env.context.get("skip_shopify_sync"):
            self._mark_for_shopify_product_export()
        return res

    def unlink(self) -> None:
        if not self.env.context.get("skip_shopify_sync"):
            self._mark_for_shopify_product_export()
        super().unlink()
