from odoo import fields, models


class CmDataPriceList(models.Model):
    _name = "integration.cm_data.price.list"
    _description = "CM Data Price List"
    _inherit = ["external.id.mixin"]
    _order = "id"

    link = fields.Text()
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
    active = fields.Boolean(default=True)
