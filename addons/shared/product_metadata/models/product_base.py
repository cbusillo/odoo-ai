import logging

from odoo import fields, models
from odoo.addons.external_ids.models.external_reference import ExternalIdBinding

_logger = logging.getLogger(__name__)

EBAY_CATEGORY_BINDING = ExternalIdBinding(system_code="ebay", resource_name="category")
EBAY_CONDITION_BINDING = ExternalIdBinding(system_code="ebay", resource_name="condition")


class ProductType(models.Model):
    _name = "product.type"
    _description = "Part Type"
    _inherit = ["external.id.mixin"]
    _external_id_binding = EBAY_CATEGORY_BINDING
    _name_uniq = models.Constraint("unique (name)", "Part Type name already exists !")

    name = fields.Char(required=True, index=True)

    products = fields.One2many("product.template", "part_type")


class ProductCondition(models.Model):
    _name = "product.condition"
    _description = "Product Condition"
    _inherit = ["external.id.mixin"]
    _external_id_binding = EBAY_CONDITION_BINDING
    _name_uniq = models.Constraint("unique (name)", "Product Condition name already exists !")

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True, readonly=True)

    products = fields.One2many("product.template", "condition")
