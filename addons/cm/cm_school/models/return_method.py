from odoo import fields, models


class ReturnMethod(models.Model):
    _name = "school.return.method"
    _description = "Return Method"
    _order = "sequence, name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="cascade",
    )
    external_key = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "return_method_unique",
            "unique(partner_id, name)",
            "Return method must be unique per partner.",
        ),
        (
            "return_method_external_key_unique",
            "unique(partner_id, external_key)",
            "Return method external key must be unique per partner.",
        ),
    ]
