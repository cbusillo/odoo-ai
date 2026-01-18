from odoo import fields, models

ALIAS_TYPES = [
    ("claim", "Claim Alias"),
    ("account", "Account Alias"),
]


class AccountAlias(models.Model):
    _name = "account.alias"
    _description = "Account Alias"
    _order = "alias"

    alias = fields.Char(required=True)
    alias_type = fields.Selection(
        ALIAS_TYPES,
        default=ALIAS_TYPES[0][0],
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
