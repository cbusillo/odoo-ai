from odoo import fields, models


class DeliveryDay(models.Model):
    _name = "school.delivery.day"
    _description = "Delivery Day"
    _order = "partner_id, sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "delivery_day_unique",
            "unique(partner_id, name)",
            "Delivery day must be unique per partner.",
        ),
    ]
