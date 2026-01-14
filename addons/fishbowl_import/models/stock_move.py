from odoo import models


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ["stock.move", "external.id.mixin"]
    _description = "Stock Move"
