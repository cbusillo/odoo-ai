from odoo import fields, models


class RepairOrder(models.Model):
    _inherit = "repair.order"

    batch_id = fields.Many2one(
        "service.repair.batch",
        ondelete="set null",
        string="Repair Batch",
    )
