from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"
    _description = "Product"

    repairs = fields.One2many("repair.order", "product_id")
    bin = fields.Char(related="product_tmpl_id.bin", readonly=False)
    is_ready_for_sale = fields.Boolean(related="product_tmpl_id.is_ready_for_sale", readonly=False)
    images = fields.One2many(related="product_tmpl_id.images", readonly=True)
    image_count = fields.Integer(related="product_tmpl_id.image_count", readonly=True)

    def update_quantity(self, quantity: float) -> None:
        stock_location_ref = "stock.stock_location_stock"
        stock_location = self.env.ref(stock_location_ref, raise_if_not_found=False)
        stock_location = stock_location.exists() if stock_location else self.env["stock.location"]
        if not stock_location:
            self.product_tmpl_id.notify_channel_on_error("Stock Location Not Found", stock_location_ref)
            return

        for product in self:
            if quantity == product.qty_available:
                continue

            quant = self.env["stock.quant"].search(
                [
                    ("product_id", "=", product.id),
                    ("location_id", "=", stock_location.id),
                ],
                limit=1,
            )

            if not quant:
                quant = self.env["stock.quant"].create({"product_id": product.id, "location_id": stock_location.id})

            quant.with_context(inventory_mode=True).write({"quantity": float(quantity)})
