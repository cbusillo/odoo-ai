from odoo import fields, models


class CmDataVacationUsage(models.Model):
    _name = "integration.cm_data.vacation.usage"
    _description = "CM Data Vacation Usage"
    _inherit = ["external.id.mixin"]
    _order = "date_of desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        ondelete="set null",
    )
    date_of = fields.Date()
    usage_hours = fields.Float()
    notes = fields.Text()
    added_by = fields.Char()
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
