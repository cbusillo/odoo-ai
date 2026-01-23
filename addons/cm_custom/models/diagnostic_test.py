from odoo import fields, models


class DiagnosticTest(models.Model):
    _name = "diagnostic.test"
    _description = "Diagnostic Test"
    _order = "name"

    name = fields.Char(required=True)
    description = fields.Text()
