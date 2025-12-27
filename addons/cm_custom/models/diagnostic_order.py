from odoo import fields, models

DIAGNOSTIC_ORDER_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("started", "Started"),
    ("finished", "Finished"),
]


class DiagnosticOrder(models.Model):
    _name = "diagnostic.order"
    _description = "Diagnostic Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    state = fields.Selection(
        DIAGNOSTIC_ORDER_STATES,
        default=DIAGNOSTIC_ORDER_STATES[0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime()
    finish_date = fields.Datetime()
    bin = fields.Char()  # TODO: needs to link to model

    devices = fields.One2many(
        "diagnostic.order.device",
        "diagnostic_order",
    )
