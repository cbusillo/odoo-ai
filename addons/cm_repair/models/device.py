from odoo import fields, models


class Device(models.Model):
    _inherit = "device"

    repair_batch_lines = fields.One2many(
        "repair.batch.device",
        "device_id",
        string="Repair Batches",
    )
