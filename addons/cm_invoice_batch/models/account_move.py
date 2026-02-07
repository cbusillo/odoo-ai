from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    invoice_batch_id = fields.Many2one(
        "service.invoice.batch",
        ondelete="set null",
        string="Invoice Batch",
    )
    invoice_order_id = fields.Many2one(
        "service.invoice.order",
        ondelete="set null",
        string="Invoice Order",
    )
