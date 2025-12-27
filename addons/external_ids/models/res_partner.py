from odoo import models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "external.id.mixin"]
    _description = "Partner"
