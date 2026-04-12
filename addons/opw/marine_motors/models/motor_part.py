from odoo import fields, models


class MotorPartTemplate(models.Model):
    _name = "motor.part.template"
    _description = "Motor Parts Available"
    _order = "sequence, id"

    name = fields.Char(required=True)
    hidden_tests = fields.Many2many("motor.test.template", string="Hidden Tests")
    hide_compression_page = fields.Boolean()
    sequence = fields.Integer(default=10, index=True)


class MotorPart(models.Model):
    _name = "motor.part"
    _description = "Motor Parts"
    _order = "sequence, id"

    motor = fields.Many2one(comodel_name="motor", required=True, ondelete="cascade")
    template = fields.Many2one(
        comodel_name="motor.part.template",
        ondelete="cascade",
    )
    name = fields.Char(related="template.name")
    sequence = fields.Integer(related="template.sequence", index=True, store=True)
    hidden_tests = fields.Many2many("motor.test.template", related="template.hidden_tests", readonly=False)
    is_missing = fields.Boolean(default=False)
