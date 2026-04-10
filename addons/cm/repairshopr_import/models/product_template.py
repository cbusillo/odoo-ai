from odoo import models


class ProductTemplate(models.Model):
    _inherit = ["product.template", "external.id.mixin"]
