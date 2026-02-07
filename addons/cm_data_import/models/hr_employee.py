from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cm_data_timeclock_id = fields.Integer()
    cm_data_repairshopr_id = fields.Integer()
    cm_data_discord_id = fields.Char()
    cm_data_grafana_username = fields.Char()
    cm_data_dept = fields.Char()
    cm_data_team = fields.Char()
    cm_data_on_site = fields.Boolean()
    cm_data_last_day = fields.Date()
