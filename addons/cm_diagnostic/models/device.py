from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    diagnostic_orders = fields.One2many(
        "service.diagnostic.order.device",
        "device",
    )
