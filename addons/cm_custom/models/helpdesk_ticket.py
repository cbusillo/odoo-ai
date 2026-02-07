from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    device_id = fields.Many2one(
        "service.device",
        ondelete="set null",
        string="Device",
    )
    transport_order_id = fields.Many2one(
        "service.transport.order",
        ondelete="set null",
        string="Transport Order",
    )
    intake_order_id = fields.Many2one(
        "service.intake.order",
        ondelete="set null",
        string="Intake Order",
    )
    repair_batch_id = fields.Many2one(
        "service.repair.batch",
        ondelete="set null",
        string="Repair Batch",
    )
    claim_id = fields.Many2one(
        "service.repair.claim",
        ondelete="set null",
    )
    claim_number = fields.Char(
        related="claim_id.claim_number",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    call_authorization_id = fields.Many2one(
        "service.call.authorization",
        ondelete="set null",
    )
    call_number = fields.Char(
        related="call_authorization_id.reference_number",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    location_option_id = fields.Many2one(
        "school.location.option",
        ondelete="set null",
        domain="['&',('location_type','=','location'),'|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    transport_location_option_id = fields.Many2one(
        "school.location.option",
        ondelete="set null",
        domain="['&',('location_type','=','transport'),'|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    transport_location_2_option_id = fields.Many2one(
        "school.location.option",
        ondelete="set null",
        domain="['&',('location_type','=','transport_2'),'|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    dropoff_location_option_id = fields.Many2one(
        "school.location.option",
        ondelete="set null",
        domain="['&',('location_type','=','dropoff'),'|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    location_raw = fields.Char(groups="base.group_system")
    location_label = fields.Char(
        related="location_option_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    location_normalized = fields.Char(groups="base.group_system")
    transport_location_label = fields.Char(
        related="transport_location_option_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    transport_location_2_label = fields.Char(
        related="transport_location_2_option_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    delivery_number = fields.Char(groups="base.group_system")
    delivery_day_id = fields.Many2one(
        "school.delivery.day",
        ondelete="set null",
        domain="['|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    return_method_id = fields.Many2one(
        "school.return.method",
        ondelete="set null",
        domain="['|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    delivery_day = fields.Char(
        related="delivery_day_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    po_number = fields.Char()
    bid_number = fields.Char()
    location_2_raw = fields.Char(groups="base.group_system")
    dropoff_location_label = fields.Char(
        related="dropoff_location_option_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    other_override_id = fields.Many2one(
        "school.override.option",
        ondelete="set null",
        domain="['|',('partner_id','=',partner_id),('partner_id','=',False)]",
    )
    other_override = fields.Char(
        related="other_override_id.name",
        store=True,
        readonly=True,
        groups="base.group_system",
    )
    billing_contract_id = fields.Many2one(
        "school.billing.contract",
        ondelete="set null",
        string="Billing Contract",
    )
    billing_policy_id = fields.Many2one(
        "school.billing.policy",
        related="billing_contract_id.policy_id",
        store=True,
        readonly=True,
    )
    billing_context_id = fields.Many2one(
        "school.billing.context",
        related="billing_contract_id.context_id",
        store=True,
        readonly=True,
    )
    billing_pricelist_id = fields.Many2one(
        "product.pricelist",
        related="billing_contract_id.pricelist_id",
        store=True,
        readonly=True,
    )

    @api.constrains(
        "billing_context_id",
        "claim_id",
        "call_authorization_id",
        "delivery_number",
        "delivery_day_id",
        "return_method_id",
        "po_number",
        "bid_number",
        "other_override_id",
        "location_option_id",
        "transport_location_option_id",
        "transport_location_2_option_id",
        "dropoff_location_option_id",
    )
    def _check_required_intake_fields(self) -> None:
        if self.env.context.get("cm_skip_required_fields"):
            return
        for ticket in self:
            if not ticket.billing_context_id:
                continue
            missing = []
            requirements = ticket.billing_context_id.requirement_ids.filtered(
                lambda requirement: requirement.is_required
                and requirement.requirement_group in {"intake", "both"}
                and requirement.target_model == "helpdesk.ticket"
                and requirement.field_name
            )
            for requirement in requirements:
                field_name = requirement.field_name
                if not hasattr(ticket, field_name):
                    missing.append(requirement.name)
                    continue
                value = ticket[field_name]
                if isinstance(value, models.BaseModel):
                    if not value:
                        missing.append(requirement.name)
                    continue
                if isinstance(value, str):
                    if not value.strip():
                        missing.append(requirement.name)
                    continue
                if not value:
                    missing.append(requirement.name)
            if missing:
                missing_list = ", ".join(missing)
                raise ValidationError(
                    f"Missing required intake fields for {ticket.billing_context_id.name}: {missing_list}"
                )
