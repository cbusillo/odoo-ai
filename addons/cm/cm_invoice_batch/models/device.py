from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    invoice_order_devices = fields.One2many(
        "service.invoice.order.device",
        "device",
        string="Invoice Orders",
    )
