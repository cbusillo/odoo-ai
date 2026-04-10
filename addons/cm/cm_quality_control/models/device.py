from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    quality_control_order_devices = fields.One2many(
        "service.quality.control.order.device",
        "device",
        string="Quality Control Orders",
    )
