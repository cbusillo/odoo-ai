from odoo import fields, models

DIAGNOSTIC_ORDER_DEVICE_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class DiagnosticOrderDevice(models.Model):
    _name = "diagnostic.order.device"
    _description = "Diagnostic Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "diagnostic_order, id"

    diagnostic_order = fields.Many2one(
        "diagnostic.order",
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        DIAGNOSTIC_ORDER_DEVICE_STATES,
        default=DIAGNOSTIC_ORDER_DEVICE_STATES[0][0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime()
    finish_date = fields.Datetime()
    device = fields.Many2one(
        "device",
        required=True,
        ondelete="restrict",
    )
    tests = fields.Many2many(
        "diagnostic.test",
        "diagnostic_order_device_test_rel",
        "diagnostic_order_device_id",
        "test_id",
    )
