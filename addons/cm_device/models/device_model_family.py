from odoo import fields, models


class DeviceModelFamily(models.Model):
    _name = "device.model.family"
    _description = "Device Model Family"
    _order = "name"

    name = fields.Char(required=True)
    models = fields.One2many(
        "device.model",
        "family",
    )
