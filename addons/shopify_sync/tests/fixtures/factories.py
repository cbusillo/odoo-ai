from collections.abc import Callable
from datetime import datetime

from odoo.api import Environment
from odoo.models import Model

from ..common_imports import common
from test_support.tests.fixtures.factories import (
    CrmTagFactory,
    CurrencyFactory,
    DeliveryCarrierFactory,
    FiscalPositionFactory,
    PartnerFactory as SharedPartnerFactory,
    ProductAttributeFactory,
    ProductFactory as SharedProductFactory,
    ProductTagFactory,
    ResUsersFactory,
    SaleOrderFactory,
    SaleOrderLineFactory,
)


def _resolve_external_id_setter(record: Model) -> Callable[..., None]:
    external_id_setter = getattr(record, "set_external_id", None)
    if not external_id_setter:
        raise AssertionError("external_ids is required for set_external_id in tests")
    return external_id_setter


class ProductFactory(SharedProductFactory):
    @classmethod
    def create(cls, environment: Environment, **kwargs: common.OdooValue) -> "odoo.model.product_template":
        shopify_product_id = kwargs.pop("shopify_product_id", None)
        shopify_variant_id = kwargs.pop("shopify_variant_id", None)
        shopify_condition_id = kwargs.pop("shopify_condition_id", None)
        shopify_ebay_category_id = kwargs.pop("shopify_ebay_category_id", None)

        kwargs.setdefault("website_description", "Test product description")

        product_template = SharedProductFactory.create(environment, **kwargs)
        product_variant = environment["product.product"].with_context(active_test=False).search(
            [("product_tmpl_id", "=", product_template.id)],
            limit=1,
        )
        if shopify_product_id or shopify_variant_id or shopify_condition_id or shopify_ebay_category_id:
            external_id_setter = _resolve_external_id_setter(product_variant)
            if shopify_product_id:
                external_id_setter("shopify", str(shopify_product_id), resource="product")
            if shopify_variant_id:
                external_id_setter("shopify", str(shopify_variant_id), resource="variant")
            if shopify_condition_id:
                external_id_setter("shopify", str(shopify_condition_id), resource="condition")
            if shopify_ebay_category_id:
                external_id_setter("shopify", str(shopify_ebay_category_id), resource="ebay_category")
        return product_template

class ShopifyProductFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: common.OdooValue) -> "odoo.model.product_template":
        defaults = {
            "shopify_sync": True,
            "shopify_inventory_item_id": common.generate_shopify_id(),
            "shopify_handle": f"test-product-{common.generate_shopify_id()}",
            "shopify_tags": "test,automated",
            "shopify_vendor": "Test Vendor",
            "shopify_product_type": "Test Type",
            "shopify_last_sync": datetime.now(),
        }
        defaults.update(kwargs)
        return ProductFactory.create(environment, **defaults)


class PartnerFactory(SharedPartnerFactory):
    @classmethod
    def create(cls, environment: Environment, **kwargs: common.OdooValue) -> "odoo.model.res_partner":
        shopify_customer_id = kwargs.pop("shopify_customer_id", None)
        shopify_address_id = kwargs.pop("shopify_address_id", None)
        ebay_username = kwargs.pop("ebay_username", None)

        partner = SharedPartnerFactory.create(environment, **kwargs)
        if shopify_customer_id or shopify_address_id or ebay_username:
            external_id_setter = _resolve_external_id_setter(partner)
            if shopify_customer_id:
                external_id_setter("shopify", str(shopify_customer_id), resource="customer")
            if shopify_address_id:
                external_id_setter("shopify", str(shopify_address_id), resource="address_invoice")
            if ebay_username:
                external_id_setter("ebay", str(ebay_username), resource="profile")
        return partner

class ShopifySyncFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: common.OdooValue) -> "odoo.model.shopify_sync":
        defaults = {
            "mode": kwargs.get("mode", "import_changed_products"),
            "start_time": datetime.now(),
        }
        defaults.update(kwargs)
        return environment["shopify.sync"].create(defaults)


__all__ = [
    "CrmTagFactory",
    "CurrencyFactory",
    "DeliveryCarrierFactory",
    "FiscalPositionFactory",
    "PartnerFactory",
    "ProductAttributeFactory",
    "ProductFactory",
    "ProductTagFactory",
    "ResUsersFactory",
    "SaleOrderFactory",
    "SaleOrderLineFactory",
    "ShopifyProductFactory",
    "ShopifySyncFactory",
]
