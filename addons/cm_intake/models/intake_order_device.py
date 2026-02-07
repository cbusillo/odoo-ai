from odoo import api, fields, models


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
    case_indicator = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("yes", "Yes"),
            ("no", "No"),
        ],
        default="unknown",
        required=True,
    )
    has_case = fields.Boolean()
    customer_stated_notes = fields.Char()
    claim_number = fields.Char()
    po_number = fields.Char()
    student_name = fields.Char()
    guardian_name = fields.Char()
    guardian_phone = fields.Char()
    needs_estimate = fields.Boolean()

    products = fields.Many2many(
        "product.template",
        "intake_order_device_product_rel",
        "intake_order_device_id",
        "product_id",
    )

    @api.onchange("case_indicator")
    def _onchange_case_indicator(self) -> None:
        if self.case_indicator == "yes":
            self.has_case = True
        elif self.case_indicator == "no":
            self.has_case = False

    @api.onchange("has_case")
    def _onchange_has_case(self) -> None:
        if self.has_case:
            self.case_indicator = "yes"
        elif self.case_indicator == "unknown":
            return
        else:
            self.case_indicator = "no"
