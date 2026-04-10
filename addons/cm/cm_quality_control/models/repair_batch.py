from odoo import fields, models


class RepairBatch(models.Model):
    _inherit = "service.repair.batch"

    quality_control_orders = fields.One2many(
        "service.quality.control.order",
        "repair_batch",
        string="Quality Control Orders",
    )
