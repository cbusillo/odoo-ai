from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import PartnerFactory, ProductFactory, SaleOrderFactory


@common.tagged(*common.UNIT_TAGS)
class TestExternalReferences(UnitTestCase):
    def test_product_reference_urls_are_declared_by_addon(self) -> None:
        product_template = ProductFactory.create(
            self.env,
            name="Shopify URL Product",
            shopify_product_id="123456",
        )
        product_variant = product_template.product_variant_id

        self.assertEqual(
            product_variant.external.shopify.product.admin_url,
            "https://admin.shopify.com/store/YOUR_STORE_KEY/products/123456",
        )
        self.assertEqual(
            product_variant.external.shopify.product.store_url,
            "https://yourstore.myshopify.com/products/123456",
        )
        self.assertEqual(
            product_template.shopify_product_admin_url,
            "https://admin.shopify.com/store/YOUR_STORE_KEY/products/123456",
        )
        self.assertEqual(
            product_template.shopify_product_url,
            "https://yourstore.myshopify.com/products/123456",
        )

    def test_partner_reference_urls_are_declared_by_addon(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Marketplace URL Partner",
            shopify_customer_id="654321",
            ebay_username="seller-name",
        )

        self.assertEqual(
            partner.external.shopify.customer.admin_url,
            "https://admin.shopify.com/store/YOUR_STORE_KEY/customers/654321",
        )
        self.assertEqual(
            partner.external.ebay.profile.profile_url,
            "https://www.ebay.com/usr/seller-name",
        )
        self.assertEqual(
            partner.shopify_customer_admin_url,
            "https://admin.shopify.com/store/YOUR_STORE_KEY/customers/654321",
        )
        self.assertEqual(partner.ebay_profile_url, "https://www.ebay.com/usr/seller-name")

    def test_bound_sale_order_reference_preserves_shopify_order_behavior(self) -> None:
        order = SaleOrderFactory.create(self.env, name="Shopify URL Order")

        order.external_reference.id = "5555555555"

        self.assertEqual(order.external_reference.id, "5555555555")
        self.assertEqual(
            order.external_reference.admin_url,
            "https://admin.shopify.com/store/YOUR_STORE_KEY/orders/5555555555",
        )
