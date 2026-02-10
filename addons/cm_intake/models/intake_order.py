from odoo import api, fields, models

INTAKE_ORDER_STATES = [
    ("started", "Started"),
    ("finished", "Finished"),
]


class IntakeOrder(models.Model):
    _name = "service.intake.order"
    _description = "Intake Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    state = fields.Selection(
        INTAKE_ORDER_STATES,
        default=INTAKE_ORDER_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "service.intake.order.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
    )
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    transport_order = fields.Many2one(
        "service.transport.order",
        ondelete="set null",
    )
    client = fields.Many2one(
        "res.partner",
        ondelete="restrict",
    )
    finish_date = fields.Datetime()
    devices = fields.One2many(
        "service.intake.order.device",
        "intake_order",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.intake.order.stage"]
        stages_by_code = {stage.code: stage for stage in stage_model.search([])}
        for order in self:
            order.stage_id = stages_by_code.get(order.state)

    def _inverse_stage_id(self) -> None:
        for order in self:
            if order.stage_id and order.stage_id.code and order.state != order.stage_id.code:
                order.state = order.stage_id.code

    @api.model
    def _read_group_stage_ids(self, stages, _domain, order=None, *_args, **_kwargs):
        return stages.search([], order=order or stages._order)


class IntakeOrderStage(models.Model):
    _name = "service.intake.order.stage"
    _description = "Intake Order Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(INTAKE_ORDER_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Intake order stage code must be unique.",
    )
