from odoo import fields, models


class IntakeOrderDevice(models.Model):
    _name = "service.intake.order.device"
    _description = "Intake Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "intake_order, id"

    intake_order = fields.Many2one(
        "service.intake.order",
        required=True,
        ondelete="cascade",
    )
    device = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    has_case = fields.Boolean()
    customer_stated_notes = fields.Char()
    claim_number = fields.Char()
    po_number = fields.Char()
    student_name = fields.Char()
    guardian_name = fields.Char()
    guardian_phone = fields.Char()

    products = fields.Many2many(
        "product.template",
        "intake_order_device_product_rel",
        "intake_order_device_id",
        "product_id",
    )
