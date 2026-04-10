from odoo import models


class HrAttendance(models.Model):
    _name = "hr.attendance"
    _inherit = ["hr.attendance", "external.id.mixin"]
