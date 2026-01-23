from odoo import fields, models


class DeviceModel(models.Model):
    _name = "service.device.model"
    _description = "Device Model"
    _inherit = ["external.id.mixin"]
    _order = "number, id"
    _rec_name = "number"

    number = fields.Char()
    family = fields.Many2one(
        "service.device.model.family",
        ondelete="set null",
    )
    products = fields.Many2many(
        "product.template",
        "device_model_product_rel",
        "device_model_id",
        "product_id",
    )
    substitute_products = fields.Many2many(
        "product.template",
        "device_model_substitute_product_rel",
        "device_model_id",
        "product_id",
    )
    devices = fields.One2many(
        "service.device",
        "model",
    )
