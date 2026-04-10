from odoo import fields, models


class LocationOption(models.Model):
    _name = "school.location.option"
    _description = "Location Option"
    _order = "partner_id, name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="cascade",
    )
    location_type = fields.Selection(
        [
            ("location", "Location"),
            ("transport", "Transport"),
            ("transport_2", "Transport 2"),
            ("dropoff", "Dropoff"),
        ],
        default="location",
        required=True,
    )
    external_key = fields.Char()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "location_option_unique",
            "unique(partner_id, location_type, name)",
            "Location option must be unique per partner and type.",
        ),
    ]
