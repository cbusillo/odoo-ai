from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    cm_data_price_list_record_ids = fields.Many2many(
        "integration.cm_data.price.list",
        "cm_data_partner_price_list_rel",
        "partner_id",
        "price_list_id",
        string="CM Data Price Lists",
    )
    cm_data_price_list_secondary_record_id = fields.Many2one(
        "integration.cm_data.price.list",
        ondelete="set null",
        string="CM Data Secondary Price List",
    )
