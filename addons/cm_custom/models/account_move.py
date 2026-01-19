from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    device_ids = fields.Many2many(
        "device",
        "move_id",
        "device_id",
        "device_account_move_rel",
        string="Devices",
    )
    source_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        ondelete="set null",
        string="Source Ticket",
    )
    repair_batch_id = fields.Many2one(
        "repair.batch",
        ondelete="set null",
        string="Repair Batch",
    )
