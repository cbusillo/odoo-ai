from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    invoice_order_id = fields.Many2one(
        "service.invoice.order",
        ondelete="set null",
        string="Invoice Order",
    )
    invoice_batch_id = fields.Many2one(
        "service.invoice.batch",
        ondelete="set null",
        string="Invoice Batch",
    )
