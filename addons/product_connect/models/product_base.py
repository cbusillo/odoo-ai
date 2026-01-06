import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductType(models.Model):
    _name = "product.type"
    _description = "Part Type"
    _name_uniq = models.Constraint("unique (name)", "Part Type name already exists !")

    name = fields.Char(required=True, index=True)
    ebay_category_id = fields.Integer(string="eBay Category ID", index=True)

    products = fields.One2many("product.template", "part_type")


class ProductCondition(models.Model):
    _name = "product.condition"
    _description = "Product Condition"
    _name_uniq = models.Constraint("unique (name)", "Product Condition name already exists !")

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True, readonly=True)
    ebay_condition_id = fields.Integer(string="eBay Condition ID", index=True)

    products = fields.One2many("product.template", "condition")
