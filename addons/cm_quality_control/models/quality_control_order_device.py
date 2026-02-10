from odoo import api, fields, models

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
    stage_id = fields.Many2one(
        "service.quality.control.order.device.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
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

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.quality.control.order.device.stage"]
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


class QualityControlOrderDeviceStage(models.Model):
    _name = "service.quality.control.order.device.stage"
    _description = "Quality Control Order Device Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(QUALITY_CONTROL_DEVICE_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Quality control order device stage code must be unique.",
    )
