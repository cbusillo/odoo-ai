from odoo import fields, models


class DeviceModel(models.Model):
    _name = "device.model"
    _description = "Device Model"
    _order = "number, id"
    _rec_name = "number"

    number = fields.Char()
    family = fields.Many2one(
        "device.model.family",
        ondelete="set null",
    )

    products = fields.Many2many(
        "product.template",
        "cm_custom_device_model_product_rel",
        "device_model_id",
        "product_id",
    )
    substitute_products = fields.Many2many(
        "product.template",
        "cm_custom_device_model_substitute_product_rel",
        "device_model_id",
        "product_id",
    )
    devices = fields.One2many(
        "device",
        "model",
    )
