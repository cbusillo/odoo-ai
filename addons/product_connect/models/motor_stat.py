from odoo import fields, models


class MotorCylinder(models.Model):
    _name = "motor.cylinder"
    _description = "Motor Cylinder Data"
    _order = "cylinder_number"
    _sql_constraints = [
        (
            "motor_cylinder_number_unique",
            "unique(motor, cylinder_number)",
            "Cylinder number must be unique per motor.",
        )
    ]

    motor = fields.Many2one("motor", ondelete="cascade")
    cylinder_number = fields.Integer(index=True)
    compression_psi = fields.Integer("Compression PSI")
    is_untestable = fields.Boolean()


class MotorImage(models.Model):
    _name = "motor.image"
    _inherit = ["image.mixin"]
    _description = "Motor Images"

    motor = fields.Many2one("motor", ondelete="cascade")
    name = fields.Char()


class MotorStroke(models.Model):
    _name = "motor.stroke"
    _description = "Motor Stroke"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, readonly=True)
    sequence = fields.Integer(default=10, index=True)

    def __str__(self) -> str:
        return self.name if self.name else ""


class MotorConfiguration(models.Model):
    _name = "motor.configuration"
    _description = "Motor Configuration"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, readonly=True)
    sequence = fields.Integer(default=10, index=True)

    def __str__(self) -> str:
        return self.name if self.name else ""
