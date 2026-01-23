from odoo import fields, models


class BillingPolicy(models.Model):
    _name = "school.billing.policy"
    _description = "Billing Policy"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    policy_type = fields.Selection(
        [
            ("hourly", "Hourly"),
            ("capped_parts_labor", "Capped Parts + Labor"),
            ("fixed_price", "Fixed Price"),
            ("time_and_materials", "Time and Materials"),
            ("no_charge", "No Charge"),
        ],
        required=True,
        default="hourly",
    )
    labor_product_id = fields.Many2one(
        "product.product",
        ondelete="set null",
    )
    labor_rate = fields.Monetary(currency_field="currency_id")
    rate_entry_mode = fields.Selection(
        [
            ("fixed_rate", "Fixed Rate"),
            ("adjust_quantity_to_target", "Adjust Quantity to Target Rate"),
        ],
        required=True,
        default="fixed_rate",
    )
    target_hourly_rate = fields.Monetary(currency_field="currency_id")
    quantity_rounding = fields.Selection(
        [
            ("no_rounding", "No Rounding"),
            ("nearest_dollar", "Nearest Dollar"),
            ("nearest_cent", "Nearest Cent"),
            ("custom", "Custom"),
        ],
        default="no_rounding",
    )
    parts_markup_percent = fields.Float()
    cap_amount = fields.Monetary(currency_field="currency_id")
    cap_labor_amount = fields.Monetary(currency_field="currency_id")
    cap_behavior = fields.Selection(
        [
            ("total_cap", "Total Cap"),
            ("parts_only_cap", "Parts Only Cap"),
            ("labor_only_cap", "Labor Only Cap"),
        ],
        default="total_cap",
    )

    _code_unique = models.Constraint("unique(code)", "Billing policy code must be unique.")
