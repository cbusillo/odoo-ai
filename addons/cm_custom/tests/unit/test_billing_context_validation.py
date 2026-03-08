from odoo.exceptions import ValidationError

from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestBillingContextValidation(UnitTestCase):
    def _create_billing_contract(
        self,
        *,
        requirement_group: str,
        field_name: str,
    ) -> "odoo.model.school_billing_contract":
        target_model = "helpdesk.ticket" if requirement_group == "intake" else "service.invoice.order"
        billing_policy = self.env["school.billing.policy"].create(
            {
                "name": f"Policy {requirement_group} {field_name}",
                "code": f"POLICY_{requirement_group}_{field_name}",
            }
        )
        billing_requirement = self.env["school.billing.requirement"].create(
            {
                "name": f"Required {field_name}",
                "code": f"REQUIRED_{requirement_group}_{field_name}",
                "requirement_group": requirement_group,
                "target_model": target_model,
                "field_name": field_name,
            }
        )
        billing_context = self.env["school.billing.context"].create(
            {
                "name": f"Context {requirement_group} {field_name}",
                "code": f"CONTEXT_{requirement_group}_{field_name}",
                "requirement_ids": [(6, 0, [billing_requirement.id])],
            }
        )
        partner = self.env["res.partner"].create({"name": f"Partner {requirement_group} {field_name}"})
        return self.env["school.billing.contract"].create(
            {
                "name": f"Contract {requirement_group} {field_name}",
                "partner_id": partner.id,
                "policy_id": billing_policy.id,
                "context_id": billing_context.id,
            }
        )

    def test_helpdesk_ticket_uses_shared_required_field_validation(self) -> None:
        billing_contract = self._create_billing_contract(
            requirement_group="intake",
            field_name="po_number",
        )
        helpdesk_team = self.env["helpdesk.team"].create({"name": "Validation Team"})

        with self.assertRaises(ValidationError):
            self.env["helpdesk.ticket"].create(
                {
                    "name": "Ticket Missing PO",
                    "team_id": helpdesk_team.id,
                    "billing_contract_id": billing_contract.id,
                }
            )

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Ticket With PO",
                "team_id": helpdesk_team.id,
                "billing_contract_id": billing_contract.id,
                "po_number": "PO-100",
            }
        )

        self.assertEqual(ticket.po_number, "PO-100")

    def test_invoice_order_uses_shared_required_field_validation(self) -> None:
        billing_contract = self._create_billing_contract(
            requirement_group="invoice",
            field_name="delivery_number",
        )

        with self.assertRaises(ValidationError):
            self.env["service.invoice.order"].create(
                {
                    "billing_contract_id": billing_contract.id,
                    "state": "ready",
                }
            )

        invoice_order = self.env["service.invoice.order"].create(
            {
                "billing_contract_id": billing_contract.id,
                "state": "ready",
                "delivery_number": "DEL-100",
            }
        )

        self.assertEqual(invoice_order.delivery_number, "DEL-100")

    def test_billing_context_validation_respects_skip_context(self) -> None:
        billing_contract = self._create_billing_contract(
            requirement_group="invoice",
            field_name="delivery_number",
        )

        invoice_order = self.env["service.invoice.order"].with_context(cm_skip_required_fields=True).create(
            {"billing_contract_id": billing_contract.id, "state": "ready"}
        )

        self.assertFalse(invoice_order.delivery_number)
