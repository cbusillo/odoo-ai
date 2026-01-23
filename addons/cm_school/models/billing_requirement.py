from odoo import fields, models


class BillingRequirement(models.Model):
    _name = "school.billing.requirement"
    _description = "Billing Requirement"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("unique(code)", "Billing requirement code must be unique.")
