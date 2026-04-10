from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    repair_batch_lines = fields.One2many(
        "service.repair.batch.device",
        "device_id",
        string="Repair Batches",
    )
