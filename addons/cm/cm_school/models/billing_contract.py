from odoo import fields, models


class BillingContract(models.Model):
    _name = "school.billing.contract"
    _description = "Billing Contract"
    _order = "partner_id, sequence, id"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    policy_id = fields.Many2one(
        "school.billing.policy",
        required=True,
        ondelete="restrict",
    )
    context_id = fields.Many2one(
        "school.billing.context",
        required=True,
        ondelete="restrict",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        ondelete="set null",
    )
    date_start = fields.Date()
    date_end = fields.Date()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
