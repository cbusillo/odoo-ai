from odoo import fields, models


class CmDataShippingInstruction(models.Model):
    _name = "integration.cm_data.shipping.instruction"
    _description = "CM Data Shipping Instruction"
    _inherit = ["external.id.mixin"]
    _order = "partner_id, address_key, id"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    address_key = fields.Char(required=True)
    inbound_carrier = fields.Char()
    inbound_service = fields.Char()
    outbound_carrier = fields.Char()
    outbound_service = fields.Char()
    to_address_name = fields.Char()
    to_address_company = fields.Char()
    to_address_street1 = fields.Char()
    to_address_street2 = fields.Char()
    to_address_city = fields.Char()
    to_address_state = fields.Char()
    to_address_zip = fields.Char()
    to_address_country = fields.Char()
    to_address_phone = fields.Char()
    to_address_email = fields.Char()
    to_address_residential_flag = fields.Boolean()
    parcel_length = fields.Float()
    parcel_width = fields.Float()
    parcel_height = fields.Float()
    parcel_weight = fields.Float()
    options_print_custom_1 = fields.Char()
    options_print_custom_2 = fields.Char()
    options_label_format = fields.Char()
    options_label_size = fields.Char()
    options_hazmat = fields.Char()
    active = fields.Boolean(default=True)
