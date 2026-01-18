from odoo import fields, models


class RepairClaim(models.Model):
    _name = "repair.claim"
    _description = "Repair Claim"
    _inherit = ["mail.thread", "mail.activity.mixin", "external.id.mixin"]
    _order = "claim_number, id"

    claim_number = fields.Char(tracking=True)
    policy_number = fields.Char()
    coverage_description = fields.Text()
    deductible_amount = fields.Float()
    incident_description = fields.Text()
    contact_name = fields.Char()
    contact_phone = fields.Char()
    shipping_address = fields.Text()
    replacement_value = fields.Float()
