from odoo import api, models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"
    _description = "Partner"

    @api.onchange("property_supplier_payment_term_id", "buyer_id", "property_outbound_payment_method_line_id")
    def _onchange_payment_terms_and_buyer(self) -> None:
        for partner in self:
            if partner.supplier_rank < 1:
                if partner.property_supplier_payment_term_id or partner.buyer_id or partner.property_outbound_payment_method_line_id:
                    partner._increase_rank("supplier_rank")
