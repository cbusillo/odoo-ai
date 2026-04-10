from odoo import fields, models

from .external_bindings import CM_DATA_PRICING_CATALOG_BINDING


class PricingCatalog(models.Model):
    _name = "school.pricing.catalog"
    _description = "Pricing Catalog"
    _inherit = ["external.id.mixin"]
    _external_id_binding = CM_DATA_PRICING_CATALOG_BINDING
    _order = "sequence, name, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    sequence = fields.Integer(default=10)
    notes = fields.Text()
    active = fields.Boolean(default=True)
    line_ids = fields.One2many(
        "school.pricing.matrix",
        "catalog_id",
        string="Pricing Lines",
    )

    _code_unique = models.Constraint("unique(code)", "Pricing catalog code must be unique.")
