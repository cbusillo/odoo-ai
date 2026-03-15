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
    claim_id = fields.Many2one(
        "service.repair.claim",
        ondelete="set null",
        string="Claim",
    )
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

    @api.model_create_multi
    def create(self, values_list: list[dict[str, object]]):
        prepared_values_list = [self._prepare_claim_values(values) for values in values_list]
        return super().create(prepared_values_list)

    def write(self, values: dict[str, object]) -> bool:
        if "claim_id" not in values and "claim_number" not in values:
            return super().write(values)

        write_succeeded = True
        for intake_order_device in self:
            prepared_values = intake_order_device._prepare_claim_values(values)
            write_succeeded = super(IntakeOrderDevice, intake_order_device).write(prepared_values) and write_succeeded
        return write_succeeded

    def _prepare_claim_values(self, values: dict[str, object]) -> dict[str, object]:
        prepared_values = dict(values)
        if "claim_id" in prepared_values:
            claim_record = self._get_claim_from_values(prepared_values)
            prepared_values["claim_number"] = getattr(claim_record, "claim_number", False) if claim_record else False
            return prepared_values
        if "claim_number" not in prepared_values:
            return prepared_values

        raw_claim_number = prepared_values.get("claim_number")
        cleaned_claim_number = str(raw_claim_number or "").strip()
        if not cleaned_claim_number:
            prepared_values["claim_id"] = False
            prepared_values["claim_number"] = False
            return prepared_values

        partner = self._get_claim_partner(prepared_values)
        claim_model = self.env["service.repair.claim"].sudo()
        claim_record = claim_model.resolve_claim(
            cleaned_claim_number,
            partner=partner,
        )
        prepared_values["claim_id"] = claim_record.id
        prepared_values["claim_number"] = getattr(claim_record, "claim_number", cleaned_claim_number)
        return prepared_values

    def _get_claim_from_values(self, values: dict[str, object]) -> models.Model:
        claim_id = self._coerce_database_id(values.get("claim_id"))
        if not claim_id:
            return self.env["service.repair.claim"].browse()
        return self.env["service.repair.claim"].browse(claim_id).exists()

    def _get_claim_partner(self, values: dict[str, object]) -> models.Model:
        intake_order_id = self._coerce_database_id(values.get("intake_order"))
        if intake_order_id:
            intake_order = self.env["service.intake.order"].browse(intake_order_id).exists()
            if intake_order:
                return intake_order.client
        if self:
            self.ensure_one()
            return self.intake_order.client
        return self.env["res.partner"].browse()

    @staticmethod
    def _coerce_database_id(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None
