from odoo import api, fields, models


class RepairClaim(models.Model):
    _name = "service.repair.claim"
    _description = "Repair Claim"
    _inherit = ["mail.thread", "mail.activity.mixin", "external.id.mixin"]
    _order = "claim_number, id"
    _rec_name = "claim_number"

    claim_number = fields.Char(tracking=True)
    partner = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    policy_number = fields.Char()
    coverage_description = fields.Text()
    deductible_amount = fields.Float()
    incident_description = fields.Text()
    contact_name = fields.Char()
    contact_phone = fields.Char()
    shipping_address = fields.Text()
    replacement_value = fields.Float()

    @api.model
    def resolve_claim(
        self,
        claim_number: str | None,
        *,
        partner: models.Model | None = None,
    ) -> models.Model:
        cleaned_claim_number = (claim_number or "").strip()
        if not cleaned_claim_number:
            return self.browse()

        claim_model = self.sudo().with_context(active_test=False)
        matching_claims = claim_model.search([("claim_number", "=", cleaned_claim_number)])
        if partner:
            exact_partner_match = matching_claims.filtered(lambda claim: claim.partner == partner)[:1]
            if exact_partner_match:
                return exact_partner_match

            partnerless_matches = matching_claims.filtered(lambda claim: not claim.partner)
            if len(partnerless_matches) == 1 and len(matching_claims) == len(partnerless_matches):
                partnerless_matches.write({"partner": partner.id})
                return partnerless_matches

        if matching_claims and not partner:
            return matching_claims[:1]

        create_values: dict[str, object] = {"claim_number": cleaned_claim_number}
        if partner:
            create_values["partner"] = partner.id
        return claim_model.create(create_values)
