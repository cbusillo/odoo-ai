from odoo import api, fields, models

REPAIR_BATCH_DEVICE_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class RepairBatchDevice(models.Model):
    _name = "repair.batch.device"
    _description = "Repair Batch Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"
    _rec_name = "device_id"

    batch_id = fields.Many2one(
        "repair.batch",
        required=True,
        ondelete="cascade",
    )
    device_id = fields.Many2one(
        "device",
        required=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        REPAIR_BATCH_DEVICE_STATES,
        default=REPAIR_BATCH_DEVICE_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "repair.batch.device.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
    )
    start_date = fields.Datetime(tracking=True)
    finish_date = fields.Datetime(tracking=True)
    issue_line_ids = fields.One2many(
        "repair.batch.device.issue",
        "device_line_id",
    )
    part_ids = fields.One2many(
        "repair.batch.device.part",
        "device_line_id",
    )

    _repair_batch_device_unique = models.Constraint(
        "unique(batch_id, device_id)",
        "A device can only appear once per repair batch.",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["repair.batch.device.stage"]
        stages_by_code = {stage.code: stage for stage in stage_model.search([])}
        for device_line in self:
            device_line.stage_id = stages_by_code.get(device_line.state)

    def _inverse_stage_id(self) -> None:
        for device_line in self:
            if device_line.stage_id and device_line.stage_id.code and device_line.state != device_line.stage_id.code:
                device_line.state = device_line.stage_id.code

    @api.model
    def _read_group_stage_ids(self, stages, _domain, order=None, *_args, **_kwargs):
        return stages.search([], order=order or stages._order)


class RepairBatchDeviceStage(models.Model):
    _name = "repair.batch.device.stage"
    _description = "Repair Batch Device Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(REPAIR_BATCH_DEVICE_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Repair batch device stage code must be unique.",
    )
