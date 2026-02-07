from odoo import fields, models

CALL_AUTHORIZATION_STATES = [
    ("draft", "Draft"),
    ("requested", "Requested"),
    ("approved", "Approved"),
    ("denied", "Denied"),
]


class CallAuthorization(models.Model):
    _name = "service.call.authorization"
    _description = "Call Authorization"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "requested_at desc, id desc"

    name = fields.Char(required=True)
    state = fields.Selection(
        CALL_AUTHORIZATION_STATES,
        default=CALL_AUTHORIZATION_STATES[0][0],
        tracking=True,
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="restrict",
        string="Vendor",
    )
    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
    )
    invoice_order_id = fields.Many2one(
        "service.invoice.order",
        ondelete="set null",
    )
    requested_at = fields.Datetime()
    approved_at = fields.Datetime()
    reference_number = fields.Char()
    notes = fields.Text(groups="base.group_system")
