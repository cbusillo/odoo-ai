from odoo import fields, models

INVOICE_NOTE_TYPES = [
    ("diagnosis", "Diagnosis"),
    ("repair", "Repair"),
    ("summary", "Summary"),
]


class InvoiceNoteTemplate(models.Model):
    _name = "service.invoice.note.template"
    _description = "Invoice Note Template"
    _order = "sequence, name"

    name = fields.Char(required=True)
    note_type = fields.Selection(
        INVOICE_NOTE_TYPES,
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    billing_context_id = fields.Many2one(
        "school.billing.context",
        ondelete="set null",
    )
    template_text = fields.Text(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
