from odoo import fields, models


ISSUE_TYPES = [
    ("missing_partner", "Missing Partner"),
    ("ambiguous_partner", "Ambiguous Partner"),
    ("missing_catalog", "Missing Catalog"),
    ("missing_product", "Missing Product"),
    ("multiple_products", "Multiple Products"),
    ("price_mismatch", "Price Mismatch"),
]


class CmDataPricingAudit(models.Model):
    _name = "integration.cm_data.pricing.audit"
    _description = "CM Data Pricing Audit"
    _order = "catalog_id, issue_type, model_label, repair_label, id"

    catalog_id = fields.Many2one(
        "school.pricing.catalog",
        ondelete="set null",
    )
    catalog_code = fields.Char()
    catalog_name = fields.Char()
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    product_id = fields.Many2one(
        "product.template",
        ondelete="set null",
    )
    issue_type = fields.Selection(
        ISSUE_TYPES,
        required=True,
    )
    model_label = fields.Char()
    repair_label = fields.Char()
    source_price = fields.Float()
    product_price = fields.Float()
    currency_id = fields.Many2one(
        "res.currency",
        ondelete="set null",
    )
    source_batch = fields.Char()
    source_file = fields.Char()
    source_catalog_id = fields.Integer()
    source_line_id = fields.Integer()
    message = fields.Text()
    active = fields.Boolean(default=True)
