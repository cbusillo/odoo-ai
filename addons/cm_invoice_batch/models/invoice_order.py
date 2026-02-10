from odoo import api, fields, models
from odoo.exceptions import ValidationError

INVOICE_ORDER_STATES = [
    ("draft", "Draft"),
    ("ready", "Ready"),
    ("invoiced", "Invoiced"),
    ("paid", "Paid"),
    ("cancelled", "Cancelled"),
]


class InvoiceOrder(models.Model):
    _name = "service.invoice.order"
    _description = "Invoice Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char()
    state = fields.Selection(
        INVOICE_ORDER_STATES,
        default=INVOICE_ORDER_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "service.invoice.order.stage",
        compute="_compute_stage_id",
        inverse="_inverse_stage_id",
        store=True,
        tracking=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        ondelete="restrict",
    )
    client = fields.Many2one(
        "res.partner",
        ondelete="restrict",
    )
    employee = fields.Many2one(
        "res.partner",
        required=True,
        default=lambda self: self.env.user.partner_id,
        ondelete="restrict",
    )
    billing_contract_id = fields.Many2one(
        "school.billing.contract",
        ondelete="set null",
    )
    billing_policy_id = fields.Many2one(
        "school.billing.policy",
        related="billing_contract_id.policy_id",
        store=True,
        readonly=True,
    )
    billing_context_id = fields.Many2one(
        "school.billing.context",
        related="billing_contract_id.context_id",
        store=True,
        readonly=True,
    )
    billing_pricelist_id = fields.Many2one(
        "product.pricelist",
        related="billing_contract_id.pricelist_id",
        store=True,
        readonly=True,
    )
    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
    )
    repair_batch_id = fields.Many2one(
        "service.repair.batch",
        ondelete="set null",
    )
    quality_control_order_id = fields.Many2one(
        "service.quality.control.order",
        ondelete="set null",
    )
    call_authorization_id = fields.Many2one(
        "service.call.authorization",
        ondelete="set null",
    )
    invoice_batch_id = fields.Many2one(
        "service.invoice.batch",
        ondelete="set null",
    )
    invoice_id = fields.Many2one(
        "account.move",
        ondelete="set null",
    )
    invoice_date = fields.Date()
    claim_id = fields.Many2one(
        "service.repair.claim",
        ondelete="set null",
    )
    claim_number = fields.Char(
        related="claim_id.claim_number",
        store=True,
        readonly=True,
    )
    call_number = fields.Char(
        related="call_authorization_id.reference_number",
        store=True,
        readonly=True,
    )
    delivery_number = fields.Char()
    po_number = fields.Char()
    bid_number = fields.Char()
    delivery_day_id = fields.Many2one(
        "school.delivery.day",
        ondelete="set null",
        domain="['|',('partner_id','=',client),('partner_id','=',False)]",
    )
    return_method_id = fields.Many2one(
        "school.return.method",
        ondelete="set null",
        domain="['|',('partner_id','=',client),('partner_id','=',False)]",
    )
    delivery_day = fields.Char(
        related="delivery_day_id.name",
        store=True,
        readonly=True,
    )
    other_override_id = fields.Many2one(
        "school.override.option",
        ondelete="set null",
        domain="['|',('partner_id','=',client),('partner_id','=',False)]",
    )
    other_override = fields.Char(
        related="other_override_id.name",
        store=True,
        readonly=True,
    )
    notes = fields.Text()
    allow_manual_notes = fields.Boolean(default=False)
    device_lines = fields.One2many(
        "service.invoice.order.device",
        "invoice_order",
        string="Devices",
    )

    @api.constrains(
        "state",
        "billing_context_id",
        "claim_id",
        "claim_number",
        "call_authorization_id",
        "call_number",
        "delivery_number",
        "delivery_day_id",
        "return_method_id",
        "po_number",
        "bid_number",
        "other_override_id",
    )
    def _check_required_invoice_fields(self) -> None:
        for order in self:
            if self.env.context.get("cm_skip_required_fields"):
                continue
            if order.state not in {"ready", "invoiced", "paid"}:
                continue
            if not order.billing_context_id:
                continue

            missing = []
            requirements = order.billing_context_id.requirement_ids.filtered(
                lambda requirement: requirement.is_required
                and requirement.requirement_group in {"invoice", "both"}
                and requirement.target_model == "service.invoice.order"
                and requirement.field_name
            )
            for requirement in requirements:
                field_name = requirement.field_name
                if not hasattr(order, field_name):
                    missing.append(requirement.name)
                    continue
                value = order[field_name]
                if isinstance(value, models.BaseModel):
                    if not value:
                        missing.append(requirement.name)
                    continue
                if isinstance(value, str):
                    if not value.strip():
                        missing.append(requirement.name)
                    continue
                if not value:
                    missing.append(requirement.name)
            if missing:
                missing_list = ", ".join(missing)
                raise ValidationError(
                    f"Missing required invoice fields for {order.billing_context_id.name}: {missing_list}"
                )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.invoice.order.stage"]
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


class InvoiceOrderStage(models.Model):
    _name = "service.invoice.order.stage"
    _description = "Invoice Order Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(INVOICE_ORDER_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Invoice order stage code must be unique.",
    )
