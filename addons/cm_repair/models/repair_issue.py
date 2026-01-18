from odoo import fields, models


class RepairIssue(models.Model):
    _name = "repair.issue"
    _description = "Repair Issue"
    _order = "name"

    name = fields.Char(required=True)
    products = fields.Many2many(
        "product.template",
        "repair_issue_product_rel",
        "repair_issue_id",
        "product_id",
    )
    compatible_products = fields.Many2many(
        "product.template",
        "repair_issue_compatible_product_rel",
        "repair_issue_id",
        "product_id",
    )
