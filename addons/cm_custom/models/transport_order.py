from odoo import fields, models

TRANSPORT_ORDER_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("transit_out", "Transit Out"),
    ("at_client", "At Client"),
    ("transit_in", "Transit In"),
    ("at_depot", "At Depot"),
    ("intake_complete", "Intake Complete"),
]

LAT_LONG_DIGITS = (10, 7)


class TransportOrder(models.Model):
    _name = "transport.order"
    _description = "Transport Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "arrival_date desc, id desc"

    name = fields.Char()
    state = fields.Selection(
        TRANSPORT_ORDER_STATES,
        default=TRANSPORT_ORDER_STATES[0],
        tracking=True,
        required=True,
    )
    arrival_date = fields.Datetime()
    departure_date = fields.Datetime()
    scheduled_date = fields.Datetime(tracking=True)
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    client = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )
    contact = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )

    quantity_in_counted = fields.Integer(tracking=True)
    quantity_out = fields.Integer(tracking=True)  # TODO: change to count of devices on order
    location_latitude = fields.Float(digits=LAT_LONG_DIGITS)
    location_longitude = fields.Float(digits=LAT_LONG_DIGITS)
    device_notes = fields.Text(tracking=True)
    devices = fields.One2many(
        "transport.order.device",
        "transport_order",
    )
