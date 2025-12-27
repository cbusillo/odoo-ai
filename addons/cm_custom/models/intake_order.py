from odoo import fields, models

INTAKE_ORDER_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class IntakeOrder(models.Model):
    _name = "intake.order"
    _description = "Intake Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    state = fields.Selection(
        INTAKE_ORDER_STATES,
        default=INTAKE_ORDER_STATES[0],
        tracking=True,
        required=True,
    )
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    transport_order = fields.Many2one(
        "transport.order",
        ondelete="set null",
    )
    client = fields.Many2one(
        "res.partner",
        ondelete="restrict",
    )
    finish_date = fields.Datetime()
    devices = fields.One2many(
        "intake.order.device",
        "intake_order",
    )
