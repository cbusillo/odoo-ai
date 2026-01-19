from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_mpn = fields.Char(string="MPN")
    x_model_number = fields.Char(string="Model Number")
    x_old_sku = fields.Char(string="Old SKU")
    x_sync_to_repairshopr = fields.Boolean(string="Sync to RepairShopr")
    x_wag_api_mapping = fields.Char(string="WAG API Mapping")
    x_sample_serial = fields.Char(string="Sample Serial")
