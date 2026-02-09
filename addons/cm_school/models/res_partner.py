from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    partner_role_ids = fields.Many2many(
        "school.partner.role",
        "school_partner_role_rel",
        "partner_id",
        "role_id",
    )

    cm_data_ticket_name = fields.Char()
    cm_data_ticket_name_report = fields.Char()
    cm_data_repairshopr_customer_id = fields.Char()
    cm_data_label_names = fields.Char()
    cm_data_location_drop = fields.Char()
    cm_data_multi_building_flag = fields.Boolean()
    cm_data_priority_flag = fields.Boolean()
    cm_data_on_delivery_schedule = fields.Boolean()
    cm_data_shipping_enable = fields.Boolean()
    cm_data_price_list_ids = fields.Char()
    cm_data_price_list_secondary_id = fields.Char()
    cm_data_contact_notes = fields.Text()
    cm_data_contact_sort_order = fields.Integer()

    billing_contract_ids = fields.One2many(
        "school.billing.contract",
        "partner_id",
        string="Billing Contracts",
    )
    billing_partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
        string="Billing Account",
    )

    routing_rule_ids = fields.One2many(
        "account.routing.rule",
        "partner_id",
        string="Routing Rules",
    )
    alias_ids = fields.One2many(
        "account.alias",
        "partner_id",
        string="Aliases",
    )
    shipping_profile_ids = fields.One2many(
        "shipping.profile",
        "partner_id",
        string="Shipping Profiles",
    )
    default_shipping_profile_id = fields.Many2one(
        "shipping.profile",
        ondelete="set null",
        string="Default Shipping Profile",
    )
