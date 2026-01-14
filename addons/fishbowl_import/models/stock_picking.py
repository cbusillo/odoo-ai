from odoo import models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "external.id.mixin"]
    _description = "Stock Picking"
