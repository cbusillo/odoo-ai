from odoo import fields, models


class OverrideOption(models.Model):
    _name = "school.override.option"
    _description = "Override Option"
    _order = "partner_id, name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="cascade",
    )
    override_type = fields.Selection(
        [
            ("other", "Other"),
            ("building", "Building"),
            ("contact", "Contact"),
        ],
        default="other",
        required=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "override_option_unique",
            "unique(partner_id, override_type, name)",
            "Override option must be unique per partner and type.",
        ),
    ]
