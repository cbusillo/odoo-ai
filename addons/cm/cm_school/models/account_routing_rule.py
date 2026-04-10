from odoo import fields, models


class AccountRoutingRule(models.Model):
    _name = "account.routing.rule"
    _description = "Account Routing Rule"
    _order = "partner_id, name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    billing_path = fields.Char()
    requires_estimate = fields.Boolean()
    pricelist_id = fields.Many2one(
        "product.pricelist",
        ondelete="set null",
    )
    default_line_item_ids = fields.Many2many(
        "product.template",
        "account_routing_rule_product_rel",
        "rule_id",
        "product_id",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)
