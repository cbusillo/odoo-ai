from odoo import fields, models


class Device(models.Model):
    _inherit = "service.device"

    intake_orders = fields.One2many(
        "service.intake.order.device",
        "device",
    )
