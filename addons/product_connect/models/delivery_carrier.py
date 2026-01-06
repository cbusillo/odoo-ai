import re
import unicodedata
from odoo import api, fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"
    _name_company_unique = models.Constraint(
        "unique(name, company_id)",
        "Carrier name must be unique per company",
    )

    service_maps = fields.One2many("delivery.carrier.service.map", "carrier")


class DeliveryCarrierServiceMap(models.Model):
    _name = "delivery.carrier.service.map"
    _description = "External ↔ Odoo shipping-service map"

    _CARRIER_PUNCTUATION_PATTERN = re.compile(r"[^\w\s]")
    _uniq_platform_service_name = models.Constraint(
        "unique(platform, platform_service_normalized_name)",
        "Duplicate service name for this platform.",
    )

    carrier = fields.Many2one(
        "delivery.carrier", required=True, ondelete="cascade", help="The Odoo delivery.carrier representing this service level."
    )
    platform = fields.Selection([("shopify", "Shopify"), ("ebay", "eBay"), ("manual", "Manual")], required=True, index=True)
    platform_service_normalized_name = fields.Char(
        required=True, index=True, help="Normalized service name from platform (e.g., 'ups ground' from Shopify, 'UPS' from eBay)"
    )
    external_id = fields.Char(help="Numeric ID when a platform sends one (e.g. eBay's ShippingService ID).")

    @api.model
    def normalize_service_name(self, name: str) -> str:
        cleaned = self._CARRIER_PUNCTUATION_PATTERN.sub(" ", name or "")
        # noinspection SpellCheckingInspection
        normalized = unicodedata.normalize("NFKD", cleaned)
        return " ".join(normalized.split()).casefold()
