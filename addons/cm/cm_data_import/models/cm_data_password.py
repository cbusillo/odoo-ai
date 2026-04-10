from odoo import fields, models


class CmDataPassword(models.Model):
    _name = "integration.cm_data.password"
    _description = "CM Data Password"
    _order = "partner_id, sub_name, user_name, id"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    sub_name = fields.Char()
    user_name = fields.Char()
    password = fields.Char()
    notes = fields.Text()
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
    active = fields.Boolean(default=True)
