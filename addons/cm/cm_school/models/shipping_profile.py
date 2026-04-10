from odoo import fields, models


class ShippingProfile(models.Model):
    _name = "shipping.profile"
    _description = "Shipping Profile"
    _order = "name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    carrier_name = fields.Char()
    service_name = fields.Char()
    instruction_notes = fields.Text()
    active = fields.Boolean(default=True)
