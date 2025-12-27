from odoo import fields, models

REPAIR_BATCH_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("started", "Started"),
    ("finished", "Finished"),
]


class RepairBatch(models.Model):
    _name = "repair.batch"
    _description = "Repair Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    name = fields.Char()
    state = fields.Selection(
        REPAIR_BATCH_STATES,
        default=REPAIR_BATCH_STATES[0][0],
        tracking=True,
        required=True,
    )
    start_date = fields.Datetime(tracking=True)
    finish_date = fields.Datetime(tracking=True)
    bin = fields.Char()
    device_line_ids = fields.One2many(
        "repair.batch.device",
        "batch_id",
        string="Devices",
    )
