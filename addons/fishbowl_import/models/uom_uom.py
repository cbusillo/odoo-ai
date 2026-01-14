from odoo import models


class UomUom(models.Model):
    _name = "uom.uom"
    _inherit = ["uom.uom", "external.id.mixin"]
    _description = "Unit of Measure"
