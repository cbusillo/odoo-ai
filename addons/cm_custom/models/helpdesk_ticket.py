from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    device_id = fields.Many2one(
        "service.device",
        ondelete="set null",
        string="Device",
    )
    transport_order_id = fields.Many2one(
        "service.transport.order",
        ondelete="set null",
        string="Transport Order",
    )
    intake_order_id = fields.Many2one(
        "service.intake.order",
        ondelete="set null",
        string="Intake Order",
    )
    repair_batch_id = fields.Many2one(
        "service.repair.batch",
        ondelete="set null",
        string="Repair Batch",
    )
    claim_number = fields.Char()
    call_number = fields.Char()
    location_raw = fields.Char()
    location_label = fields.Char()
    location_normalized = fields.Char()
    transport_location_label = fields.Char()
    transport_location_2_label = fields.Char()
    delivery_number = fields.Char()
    bid_number = fields.Char()
    location_2_raw = fields.Char()
    dropoff_location_label = fields.Char()
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
    )
