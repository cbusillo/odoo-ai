from odoo import fields, models


class ProductImage(models.Model):
    _name = "product.image"
    _inherit = ["image.metadata.mixin", "product.image"]

    initial_index = fields.Integer()
