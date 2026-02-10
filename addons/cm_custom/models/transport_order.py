from odoo import api, fields, models

TRANSPORT_ORDER_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("transit_out", "Transit Out"),
    ("at_client", "At Client"),
    ("transit_in", "Transit In"),
    ("at_depot", "At Depot"),
    ("intake_complete", "Intake Complete"),
]

LAT_LONG_DIGITS = (10, 7)


class TransportOrder(models.Model):
    _name = "transport.order"
    _description = "Transport Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "arrival_date desc, id desc"

    name = fields.Char()
    state = fields.Selection(
        TRANSPORT_ORDER_STATES,
        default=TRANSPORT_ORDER_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "transport.order.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
    )
    arrival_date = fields.Datetime()
    departure_date = fields.Datetime()
    scheduled_date = fields.Datetime(tracking=True)
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    client = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )
    contact = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )

    quantity_in_counted = fields.Integer(tracking=True)
    quantity_out = fields.Integer(tracking=True)  # TODO: change to count of devices on order
    location_latitude = fields.Float(digits=LAT_LONG_DIGITS)
    location_longitude = fields.Float(digits=LAT_LONG_DIGITS)
    device_notes = fields.Text(tracking=True)
    devices = fields.One2many(
        "transport.order.device",
        "transport_order",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["transport.order.stage"]
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


class TransportOrderStage(models.Model):
    _name = "transport.order.stage"
    _description = "Transport Order Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(TRANSPORT_ORDER_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Transport order stage code must be unique.",
    )
