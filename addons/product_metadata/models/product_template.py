import re

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    mpn = fields.Char(string="MPN", index=True)
    first_mpn = fields.Char(compute="_compute_first_mpn", store=True)
    manufacturer = fields.Many2one("product.manufacturer", index=True)
    vendor = fields.Many2one(
        "res.partner",
        domain=[("supplier_rank", ">", 0)],
    )
    part_type = fields.Many2one("product.type", index=True)
    part_type_name = fields.Char(related="part_type.name", store=True, index=True, string="Part Type Name")
    condition = fields.Many2one("product.condition", index=True)

    @api.depends("mpn")
    def _compute_first_mpn(self) -> None:
        for product in self:
            mpns = product.get_list_of_mpns()
            product.first_mpn = mpns[0] if mpns else ""

    def get_list_of_mpns(self) -> list[str]:
        self.ensure_one()
        if not self.mpn or not self.mpn.strip():
            return []
        mpn_parts = re.split(r"[, ]", self.mpn)
        return [mpn.strip() for mpn in mpn_parts if mpn.strip()]

    @api.constrains("mpn")
    def _check_mpn_format(self) -> None:
        self._onchange_format_mpn_upper()

    @api.onchange("mpn")
    def _onchange_format_mpn_upper(self) -> None:
        for product in self.filtered(lambda p: p.mpn and p.mpn.upper() != p.mpn):
            product.mpn = product.mpn.upper()
