from odoo import fields, models

QUALITY_CONTROL_DEVICE_STATES = [
    ("pending", "Pending"),
    ("started", "Started"),
    ("passed", "Passed"),
    ("failed", "Failed"),
]


class QualityControlOrderDevice(models.Model):
    _name = "service.quality.control.order.device"
    _description = "Quality Control Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "quality_control_order, id"

    quality_control_order = fields.Many2one(
        "service.quality.control.order",
        required=True,
        ondelete="cascade",
    )
    device = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    repair_batch_device = fields.Many2one(
        "service.repair.batch.device",
        ondelete="set null",
    )
    state = fields.Selection(
        QUALITY_CONTROL_DEVICE_STATES,
        default=QUALITY_CONTROL_DEVICE_STATES[0][0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime()
    finish_date = fields.Datetime()
    summary_note = fields.Text()
    results = fields.One2many(
        "service.quality.control.result",
        "quality_control_order_device",
        string="Checklist Results",
    )

    _sql_constraints = [
        (
            "quality_control_order_device_unique",
            "unique(quality_control_order, device)",
            "A device can only appear once per quality control order.",
        ),
    ]
