from odoo import fields, models

QUALITY_CONTROL_ORDER_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("started", "Started"),
    ("finished", "Finished"),
]


class QualityControlOrder(models.Model):
    _name = "service.quality.control.order"
    _description = "Quality Control Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    name = fields.Char()
    state = fields.Selection(
        QUALITY_CONTROL_ORDER_STATES,
        default=QUALITY_CONTROL_ORDER_STATES[0][0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime()
    finish_date = fields.Datetime()
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    client = fields.Many2one(
        "res.partner",
        ondelete="restrict",
    )
    repair_batch = fields.Many2one(
        "service.repair.batch",
        ondelete="set null",
    )
    notes = fields.Text()
    devices = fields.One2many(
        "service.quality.control.order.device",
        "quality_control_order",
        string="Devices",
    )
