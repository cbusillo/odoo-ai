from odoo import fields, models


class PartnerRole(models.Model):
    _name = "cm.partner.role"
    _description = "CM Partner Role"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("unique(code)", "Partner role code must be unique.")
