from odoo import api, fields, models

INVOICE_BATCH_STATES = [
    ("draft", "Draft"),
    ("prepared", "Prepared"),
    ("sent", "Sent"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

INVOICE_BATCH_TYPES = [
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("ad_hoc", "Ad Hoc"),
]


class InvoiceBatch(models.Model):
    _name = "service.invoice.batch"
    _description = "Invoice Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, id desc"

    name = fields.Char()
    batch_type = fields.Selection(
        INVOICE_BATCH_TYPES,
        default=INVOICE_BATCH_TYPES[0][0],
        required=True,
    )
    state = fields.Selection(
        INVOICE_BATCH_STATES,
        default=INVOICE_BATCH_STATES[0][0],
        tracking=True,
        required=True,
    )
    stage_id = fields.Many2one(
        "service.invoice.batch.stage",
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
    )
    billing_contract_id = fields.Many2one(
        "school.billing.contract",
        ondelete="set null",
    )
    billing_context_id = fields.Many2one(
        "school.billing.context",
        related="billing_contract_id.context_id",
        store=True,
        readonly=True,
    )
    period_start = fields.Date()
    period_end = fields.Date()
    invoice_date = fields.Date()
    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
    )
    notes = fields.Text()
    line_ids = fields.One2many(
        "service.invoice.batch.line",
        "invoice_batch",
        string="Line Items",
    )
    invoice_ids = fields.Many2many(
        "account.move",
        "service_invoice_batch_move_rel",
        "batch_id",
        "move_id",
        domain="[('move_type', 'in', ['out_invoice', 'out_refund'])]",
        string="Invoices",
    )
    invoice_orders = fields.One2many(
        "service.invoice.order",
        "invoice_batch_id",
        string="Invoice Orders",
    )

    @api.depends("state")
    def _compute_stage_id(self) -> None:
        stage_model = self.env["service.invoice.batch.stage"]
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


class InvoiceBatchStage(models.Model):
    _name = "service.invoice.batch.stage"
    _description = "Invoice Batch Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Selection(INVOICE_BATCH_STATES, required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Invoice batch stage code must be unique.",
    )


class InvoiceBatchLine(models.Model):
    _name = "service.invoice.batch.line"
    _description = "Invoice Batch Line"
    _order = "sequence, id"

    invoice_batch = fields.Many2one(
        "service.invoice.batch",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="restrict",
        string="District",
    )
    description = fields.Text()
    reference_numbers = fields.Text()
    hours = fields.Float()
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(currency_field="currency_id")
