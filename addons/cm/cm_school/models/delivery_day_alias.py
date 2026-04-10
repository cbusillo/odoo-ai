from odoo import fields, models


class DeliveryDayAlias(models.Model):
    _name = "school.delivery.day.alias"
    _description = "Delivery Day Alias"
    _order = "external_key, id"

    delivery_day_id = fields.Many2one(
        "school.delivery.day",
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
            "delivery_day_alias_unique",
            "unique(system_id, external_key)",
            "Delivery day alias must be unique per system and key.",
        ),
    ]
