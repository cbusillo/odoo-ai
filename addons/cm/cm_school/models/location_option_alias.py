from odoo import fields, models


class LocationOptionAlias(models.Model):
    _name = "school.location.option.alias"
    _description = "Location Option Alias"
    _order = "external_key, id"

    location_option_id = fields.Many2one(
        "school.location.option",
        required=True,
        ondelete="cascade",
    )
    system_id = fields.Many2one(
        "external.system",
        required=True,
        ondelete="restrict",
    )
    external_key = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "location_option_alias_unique",
            "unique(system_id, external_key)",
            "Location option alias must be unique per system and key.",
        ),
    ]
