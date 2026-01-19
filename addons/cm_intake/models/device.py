from odoo import fields, models


class Device(models.Model):
    _inherit = "device"

    intake_orders = fields.One2many(
        "intake.order.device",
        "device",
    )
