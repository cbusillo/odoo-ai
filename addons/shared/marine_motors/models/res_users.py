from odoo import fields, models


class Users(models.Model):
    _name = "res.users"
    _inherit = "res.users"

    folded_motor_stages = fields.Many2many("motor.stage", "folded_motor_stage_user_rel", "user_id", "setting_id")

    def __str__(self) -> str:
        return self.name if self.name else ""
