from odoo import fields, models


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee", "external.id.mixin"]

    cm_data_grafana_username = fields.Char()
    cm_data_dept = fields.Char()
    cm_data_team = fields.Char()
    cm_data_on_site = fields.Boolean()
    cm_data_last_day = fields.Date()
