from odoo import fields, models


class BillingContext(models.Model):
    _name = "school.billing.context"
    _description = "Billing Context"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    description = fields.Text()
    requirement_ids = fields.Many2many(
        "school.billing.requirement",
        "school_billing_context_requirement_rel",
        "context_id",
        "requirement_id",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("unique(code)", "Billing context code must be unique.")
