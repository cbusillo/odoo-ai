from typing import Final

from odoo.addons.external_ids.models.external_reference import (
    ExternalIdBinding,
    ExternalResourceReference,
    ExternalSystemReference,
    external_url_field,
    register_external_system_reference,
)


class ShopifyProductReference(ExternalResourceReference):
    admin_url = external_url_field("admin")
    store_url = external_url_field("store")


class ShopifyCustomerReference(ExternalResourceReference):
    admin_url = external_url_field("admin")


class ShopifyOrderReference(ExternalResourceReference):
    admin_url = external_url_field("admin")


class ShopifyOrderLineReference(ExternalResourceReference):
    pass


class ShopifyAddressReference(ExternalResourceReference):
    pass


class ShopifyMediaReference(ExternalResourceReference):
    pass


class ShopifyVariantReference(ExternalResourceReference):
    pass


class ShopifyConditionReference(ExternalResourceReference):
    pass


class ShopifyEbayCategoryReference(ExternalResourceReference):
    pass


class ShopifyReference(ExternalSystemReference):
    _resource_reference_classes = {
        "address": ShopifyAddressReference,
        "address_delivery": ShopifyAddressReference,
        "address_invoice": ShopifyAddressReference,
        "condition": ShopifyConditionReference,
        "customer": ShopifyCustomerReference,
        "ebay_category": ShopifyEbayCategoryReference,
        "media": ShopifyMediaReference,
        "order": ShopifyOrderReference,
        "order_line": ShopifyOrderLineReference,
        "product": ShopifyProductReference,
        "variant": ShopifyVariantReference,
    }

class EbayProfileReference(ExternalResourceReference):
    profile_url = external_url_field("profile")


class EbayCategoryReference(ExternalResourceReference):
    pass


class EbayOrderReference(ExternalResourceReference):
    pass


SHOPIFY_ORDER_BINDING: Final[ExternalIdBinding] = ExternalIdBinding(system_code="shopify", resource_name="order")
SHOPIFY_ORDER_LINE_BINDING: Final[ExternalIdBinding] = ExternalIdBinding(system_code="shopify", resource_name="order_line")


class EbayReference(ExternalSystemReference):
    _resource_reference_classes = {
        "category": EbayCategoryReference,
        "order": EbayOrderReference,
        "profile": EbayProfileReference,
    }


register_external_system_reference("shopify", ShopifyReference)
register_external_system_reference("ebay", EbayReference)
