from odoo import fields, models


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "external.id.mixin"]

    shopify_last_exported_at = fields.Datetime(string="Last Exported Time")
    shopify_next_export = fields.Boolean(string="Export Next Sync?")
    shopify_next_export_quantity_change_amount = fields.Integer()
    shopify_created_at = fields.Datetime()
