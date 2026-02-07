from odoo import api, fields, models

INVOICE_ORDER_DEVICE_STATUSES = [
    ("pending", "Pending"),
    ("ready", "Ready"),
    ("invoiced", "Invoiced"),
]

INVOICE_UPDATE_STATUSES = [
    ("repaired", "Repaired"),
    ("motherboard_repair", "Motherboard Repair"),
    ("not_repaired", "Not Repaired"),
]


class InvoiceOrderDevice(models.Model):
    _name = "service.invoice.order.device"
    _description = "Invoice Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "invoice_order, id"

    invoice_order = fields.Many2one(
        "service.invoice.order",
        required=True,
        ondelete="cascade",
    )
    device = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    quality_control_order_device = fields.Many2one(
        "service.quality.control.order.device",
        ondelete="set null",
    )
    diagnosis_template_id = fields.Many2one(
        "service.invoice.note.template",
        ondelete="set null",
        domain="[('note_type', '=', 'diagnosis')]")
    repair_template_id = fields.Many2one(
        "service.invoice.note.template",
        ondelete="set null",
        domain="[('note_type', '=', 'repair')]")
    summary_template_id = fields.Many2one(
        "service.invoice.note.template",
        ondelete="set null",
        domain="[('note_type', '=', 'summary')]")
    state = fields.Selection(
        INVOICE_ORDER_DEVICE_STATUSES,
        default=INVOICE_ORDER_DEVICE_STATUSES[0][0],
        required=True,
        tracking=True,
    )
    diagnosis_note = fields.Text()
    repair_note = fields.Text()
    summary_note = fields.Text()
    update_status = fields.Selection(
        INVOICE_UPDATE_STATUSES,
    )
    needs_estimate = fields.Boolean()
    is_capped_pricing = fields.Boolean()
    capped_amount = fields.Monetary(
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )

    _sql_constraints = [
        (
            "invoice_order_device_unique",
            "unique(invoice_order, device)",
            "A device can only appear once per invoice order.",
        ),
    ]

    @api.onchange("diagnosis_template_id")
    def _onchange_diagnosis_template_id(self) -> None:
        if self.diagnosis_template_id and not self.diagnosis_note:
            self.diagnosis_note = self.diagnosis_template_id.template_text

    @api.onchange("repair_template_id")
    def _onchange_repair_template_id(self) -> None:
        if self.repair_template_id and not self.repair_note:
            self.repair_note = self.repair_template_id.template_text

    @api.onchange("summary_template_id")
    def _onchange_summary_template_id(self) -> None:
        if self.summary_template_id and not self.summary_note:
            self.summary_note = self.summary_template_id.template_text
