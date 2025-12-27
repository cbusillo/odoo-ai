from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _name = "res.config.settings"
    _inherit = "res.config.settings"

    user_name_format = fields.Selection(
        selection=[
            ("western", "Western: First Last"),
            ("asian", "Asian: Last First"),
            ("custom", "Custom Pattern"),
        ],
        default="western",
        string="Employee Name Format",
        config_parameter="user_name_extended.format",
    )

    user_name_custom_pattern = fields.Char(
        string="Custom Name Pattern",
        config_parameter="user_name_extended.custom_pattern",
    )
