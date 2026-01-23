from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    transport_orders = fields.One2many(
        "service.transport.order.device",
        "device",
    )
