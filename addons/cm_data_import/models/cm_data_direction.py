from odoo import fields, models


class CmDataDirection(models.Model):
    _name = "integration.cm_data.direction"
    _description = "CM Data Direction"
    _inherit = ["external.id.mixin"]
    _order = "partner_id, delivery_order, id"

    name = fields.Char()
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    ticket_title_name = fields.Char()
    school_name = fields.Char()
    delivery_day = fields.Char()
    address = fields.Text()
    directions = fields.Text()
    contact = fields.Text()
    priority = fields.Boolean()
    on_schedule_flag = fields.Boolean()
    delivery_order = fields.Float()
    longitude = fields.Float()
    latitude = fields.Float()
    available_start = fields.Char()
    available_end = fields.Char()
    break_start = fields.Char()
    break_end = fields.Char()
    est_arrival_time = fields.Char()
    shipping_enabled_flag = fields.Boolean()
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
    active = fields.Boolean(default=True)
