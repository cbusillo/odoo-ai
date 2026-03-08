from odoo import fields, models
from odoo.exceptions import ValidationError


class BillingContext(models.Model):
    _name = "school.billing.context"
    _description = "Billing Context"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    description = fields.Text()
    requirement_ids = fields.Many2many(
        "school.billing.requirement",
        "school_billing_context_requirement_rel",
        "context_id",
        "requirement_id",
    )
    requires_estimate = fields.Boolean(default=False)
    requires_claim_approval = fields.Boolean(default=False)
    requires_call_authorization = fields.Boolean(default=False)
    requires_payment_on_pickup = fields.Boolean(default=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("unique(code)", "Billing context code must be unique.")

    @staticmethod
    def _is_missing_required_value(value: object) -> bool:
        if isinstance(value, models.BaseModel):
            return not bool(value)
        if isinstance(value, str):
            return not value.strip()
        return not bool(value)

    def get_missing_required_field_names(
        self,
        record: models.Model,
        *,
        requirement_group: str,
        target_model: str,
    ) -> list[str]:
        self.ensure_one()
        missing_field_names: list[str] = []
        requirements = self.requirement_ids.filtered(
            lambda billing_requirement: billing_requirement.is_required
            and billing_requirement.requirement_group in {requirement_group, "both"}
            and billing_requirement.target_model == target_model
            and billing_requirement.field_name
        )
        for requirement in requirements:
            field_name = requirement.field_name
            if field_name not in record._fields:
                missing_field_names.append(requirement.name)
                continue
            if self._is_missing_required_value(record[field_name]):
                missing_field_names.append(requirement.name)
        return missing_field_names

    def validate_required_fields(
        self,
        record: models.Model,
        *,
        requirement_group: str,
        target_model: str,
        workflow_label: str,
    ) -> None:
        self.ensure_one()
        missing_field_names = self.get_missing_required_field_names(
            record,
            requirement_group=requirement_group,
            target_model=target_model,
        )
        if missing_field_names:
            missing_list = ", ".join(missing_field_names)
            raise ValidationError(f"Missing required {workflow_label} fields for {self.name}: {missing_list}")
