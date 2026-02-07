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
    is_required = fields.Boolean(default=True)
    requirement_group = fields.Selection(
        [
            ("intake", "Intake"),
            ("invoice", "Invoice"),
            ("both", "Both"),
        ],
        default="both",
        required=True,
    )
    target_model = fields.Selection(
        [
            ("helpdesk.ticket", "Helpdesk Ticket"),
            ("service.invoice.order", "Invoice Order"),
        ],
    )
    field_name = fields.Char()

    _code_unique = models.Constraint("unique(code)", "Billing requirement code must be unique.")
