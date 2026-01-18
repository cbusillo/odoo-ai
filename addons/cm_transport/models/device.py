from odoo import fields, models


class Device(models.Model):
    _inherit = "device"

    transport_orders = fields.One2many(
        "transport.order.device",
        "device",
    )
