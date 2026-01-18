from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    device_id = fields.Many2one(
        "device",
        ondelete="set null",
        string="Device",
    )
    transport_order_id = fields.Many2one(
        "transport.order",
        ondelete="set null",
        string="Transport Order",
    )
    intake_order_id = fields.Many2one(
        "intake.order",
        ondelete="set null",
        string="Intake Order",
    )
    repair_batch_id = fields.Many2one(
        "repair.batch",
        ondelete="set null",
        string="Repair Batch",
    )
    claim_number = fields.Char()
    location_raw = fields.Char()
    location_label = fields.Char()
    location_normalized = fields.Char()
    transport_location_label = fields.Char()
    transport_location_2_label = fields.Char()
    delivery_number = fields.Char()
    bid_number = fields.Char()
    location_2_raw = fields.Char()
    dropoff_location_label = fields.Char()
