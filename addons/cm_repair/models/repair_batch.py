from odoo import api, fields, models

REPAIR_BATCH_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("started", "Started"),
    ("finished", "Finished"),
]


class RepairBatch(models.Model):
    _name = "service.repair.batch"
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
    stage_id = fields.Many2one(
        "service.repair.batch.stage",
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
    bin = fields.Char()
    device_line_ids = fields.One2many(
        "service.repair.batch.device",
        "batch_id",
        string="Devices",
    )
    repair_order_ids = fields.One2many(
        "repair.order",
        "batch_id",
        string="Repair Orders",
    )
    ticket_ids = fields.Many2many(
        "helpdesk.ticket",
        "repair_batch_helpdesk_ticket_rel",
        "batch_id",
        "ticket_id",
        string="Tickets",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.repair.batch.stage"]
        stages_by_code = {stage.code: stage for stage in stage_model.search([])}
        for batch in self:
            batch.stage_id = stages_by_code.get(batch.state)

    def _inverse_stage_id(self) -> None:
        for batch in self:
            if batch.stage_id and batch.stage_id.code and batch.state != batch.stage_id.code:
                batch.state = batch.stage_id.code

    @api.model
    def _read_group_stage_ids(self, stages, _domain, order=None, *_args, **_kwargs):
        return stages.search([], order=order or stages._order)


class RepairBatchStage(models.Model):
    _name = "service.repair.batch.stage"
    _description = "Repair Batch Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(REPAIR_BATCH_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Repair batch stage code must be unique.",
    )
