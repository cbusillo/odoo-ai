from odoo import fields, models

REPAIR_BATCH_DEVICE_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class RepairBatchDevice(models.Model):
    _name = "service.repair.batch.device"
    _description = "Repair Batch Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"
    _rec_name = "device_id"

    batch_id = fields.Many2one(
        "service.repair.batch",
        required=True,
        ondelete="cascade",
    )
    device_id = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        REPAIR_BATCH_DEVICE_STATES,
        default=REPAIR_BATCH_DEVICE_STATES[0][0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime(tracking=True)
    finish_date = fields.Datetime(tracking=True)
    issue_line_ids = fields.One2many(
        "service.repair.batch.device.issue",
        "device_line_id",
    )
    part_ids = fields.One2many(
        "service.repair.batch.device.part",
        "device_line_id",
    )

    _repair_batch_device_unique = models.Constraint(
        "unique(batch_id, device_id)",
        "A device can only appear once per repair batch.",
    )
