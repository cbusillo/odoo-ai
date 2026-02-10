from odoo import api, fields, models

DIAGNOSTIC_ORDER_DEVICE_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class DiagnosticOrderDevice(models.Model):
    _name = "service.diagnostic.order.device"
    _description = "Diagnostic Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "diagnostic_order, id"

    diagnostic_order = fields.Many2one(
        "service.diagnostic.order",
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        DIAGNOSTIC_ORDER_DEVICE_STATES,
        default=DIAGNOSTIC_ORDER_DEVICE_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "service.diagnostic.order.device.stage",
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
    device = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    tests = fields.Many2many(
        "service.diagnostic.test",
        "service_diagnostic_order_device_test_rel",
        "diagnostic_order_device_id",
        "test_id",
    )
    results = fields.One2many(
        "service.diagnostic.result",
        "diagnostic_order_device",
        string="Test Results",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.diagnostic.order.device.stage"]
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


class DiagnosticOrderDeviceStage(models.Model):
    _name = "service.diagnostic.order.device.stage"
    _description = "Diagnostic Order Device Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(DIAGNOSTIC_ORDER_DEVICE_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Diagnostic order device stage code must be unique.",
    )
