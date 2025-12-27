from odoo import fields, models


class IntakeOrderDevice(models.Model):
    _name = "intake.order.device"
    _description = "Intake Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "intake_order, id"

    intake_order = fields.Many2one(
        "intake.order",
        required=True,
        ondelete="cascade",
    )
    device = fields.Many2one(
        "device",
        required=True,
        ondelete="restrict",
    )
    has_case = fields.Boolean()
    customer_stated_notes = fields.Char()

    products = fields.Many2many(
        "product.template",
        "intake_order_device_product_rel",
        "intake_order_device_id",
        "product_id",
    )
