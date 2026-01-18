from odoo import fields, models


class Device(models.Model):
    _inherit = "device"

    diagnostic_orders = fields.One2many(
        "diagnostic.order.device",
        "device",
    )
