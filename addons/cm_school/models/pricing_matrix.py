from odoo import api, fields, models


class PricingMatrix(models.Model):
    _name = "school.pricing.matrix"
    _description = "Pricing Matrix"
    _inherit = ["external.id.mixin"]
    _order = "catalog_id, contract_id, device_model_id, model_label, repair_label, effective_date, id"

    name = fields.Char()
    contract_id = fields.Many2one(
        "school.billing.contract",
        ondelete="cascade",
    )
    policy_id = fields.Many2one(
        "school.billing.policy",
        related="contract_id.policy_id",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        compute="_compute_partner_id",
        store=True,
        readonly=True,
    )
    context_id = fields.Many2one(
        "school.billing.context",
        related="contract_id.context_id",
        store=True,
        readonly=True,
    )
    catalog_id = fields.Many2one(
        "school.pricing.catalog",
        ondelete="set null",
    )
    model_label = fields.Char()
    repair_label = fields.Char()
    device_model_id = fields.Many2one(
        "service.device.model",
        ondelete="set null",
    )
    part_product_id = fields.Many2one(
        "product.template",
        ondelete="set null",
    )
    price = fields.Monetary(currency_field="currency_id")
    company_id = fields.Many2one(
        "res.company",
        compute="_compute_company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    effective_date = fields.Date()
    expires_at = fields.Date()
    active = fields.Boolean(default=True)

    @api.depends("contract_id.partner_id", "catalog_id.partner_id")
    def _compute_partner_id(self) -> None:
        for record in self:
            record.partner_id = record.contract_id.partner_id or record.catalog_id.partner_id

    @api.depends("contract_id.company_id")
    def _compute_company_id(self) -> None:
        for record in self:
            record.company_id = record.contract_id.company_id or self.env.company
