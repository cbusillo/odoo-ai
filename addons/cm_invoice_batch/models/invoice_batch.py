from odoo import fields, models

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
