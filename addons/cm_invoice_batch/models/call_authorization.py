from odoo import api, fields, models

CALL_AUTHORIZATION_STATES = [
    ("draft", "Draft"),
    ("requested", "Requested"),
    ("approved", "Approved"),
    ("denied", "Denied"),
]


class CallAuthorization(models.Model):
    _name = "service.call.authorization"
    _description = "Call Authorization"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "requested_at desc, id desc"

    name = fields.Char(required=True)
    state = fields.Selection(
        CALL_AUTHORIZATION_STATES,
        default=CALL_AUTHORIZATION_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "service.call.authorization.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
    )
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="restrict",
        string="Vendor",
    )
    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
    )
    invoice_order_id = fields.Many2one(
        "service.invoice.order",
        ondelete="set null",
    )
    requested_at = fields.Datetime()
    approved_at = fields.Datetime()
    reference_number = fields.Char()
    notes = fields.Text(groups="base.group_system")

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.call.authorization.stage"]
        stages_by_code = {stage.code: stage for stage in stage_model.search([])}
        for authorization in self:
            authorization.stage_id = stages_by_code.get(authorization.state)

    def _inverse_stage_id(self) -> None:
        for authorization in self:
            if authorization.stage_id and authorization.stage_id.code and authorization.state != authorization.stage_id.code:
                authorization.state = authorization.stage_id.code

    @api.model
    def _read_group_stage_ids(self, stages, _domain, order=None, *_args, **_kwargs):
        return stages.search([], order=order or stages._order)


class CallAuthorizationStage(models.Model):
    _name = "service.call.authorization.stage"
    _description = "Call Authorization Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(CALL_AUTHORIZATION_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Call authorization stage code must be unique.",
    )
