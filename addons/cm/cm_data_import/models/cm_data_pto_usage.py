from odoo import fields, models


class CmDataPtoUsage(models.Model):
    _name = "integration.cm_data.pto.usage"
    _description = "CM Data PTO Usage"
    _inherit = ["external.id.mixin"]
    _order = "used_at desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        ondelete="set null",
    )
    used_at = fields.Datetime()
    pay_period_ending = fields.Date()
    usage_hours = fields.Float()
    notes = fields.Text()
    added_by = fields.Char()
    source_updated_at = fields.Datetime()
