from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    billing_contract_id = fields.Many2one(
        "school.billing.contract",
        ondelete="set null",
        string="Billing Contract",
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
        string="Billing Pricelist",
    )
    source_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
        string="Source Ticket",
    )
