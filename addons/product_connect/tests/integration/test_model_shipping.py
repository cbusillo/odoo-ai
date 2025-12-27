from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import (
    ShopifySyncFactory,
    PartnerFactory,
    CurrencyFactory,
    ProductFactory,
    DeliveryCarrierFactory,
    SaleOrderFactory,
    SaleOrderLineFactory,
)
import logging

_logger = logging.getLogger(__name__)


@tagged(*INTEGRATION_TAGS)
class TestShipping(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, skip_shopify_sync=True, tracking_disable=True))
        cls._create_test_data()

    @classmethod
    def _create_test_data(cls) -> None:
        cls.usd_currency = cls.env["res.currency"].search([("name", "=", "USD")], limit=1)
        if not cls.usd_currency:
            cls.usd_currency = CurrencyFactory.create(cls.env, name="USD", symbol="$", rate=1.0)

        cls.partner = PartnerFactory.create(
            cls.env,
            name="Test Shipping Customer",
            email="shipping@test.com",
        )

        cls.product = ProductFactory.create(
            cls.env,
            name="Test Shipping Product",
            default_code="12345",
            type="consu",
            list_price=100.0,
        ).product_variant_id

        cls.delivery_product = ProductFactory.create(
            cls.env,
            name="Test Delivery Service",
            default_code="99999",
            type="service",
            list_price=0.0,
        ).product_variant_id

        cls.carrier = DeliveryCarrierFactory.create(
            cls.env,
            name="Test Shipping Carrier",
            delivery_type="fixed",
            fixed_price=10.0,
            product_id=cls.delivery_product.id,
        )

    def test_shipping_fields_default_values(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
        )

        self.assertEqual(order.shipping_charge, 0.0)
        self.assertEqual(order.shipping_paid, 0.0)
        self.assertEqual(order.shipping_margin, 0.0)
        self.assertFalse(order.source_platform)
        self.assertFalse(order.shopify_order_id)
        self.assertFalse(order.ebay_order_id)
        self.assertFalse(order.shipstation_order_id)
        self.assertFalse(order.shipping_tracking_numbers)

    def test_shipping_margin_calculation(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            currency_id=self.usd_currency.id,
            shipping_charge=25.00,
            shipping_paid=18.50,
        )

        self.assertEqual(order.shipping_margin, 6.50)

        order.shipping_paid = 30.00
        self.assertEqual(order.shipping_margin, -5.00)

        order.write(
            {
                "shipping_charge": 50.0,
                "shipping_paid": 30.0,
            }
        )
        self.assertEqual(order.shipping_margin, 20.0)

    def test_source_platform_values(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            source_platform="shopify",
            shopify_order_id="SHOP123456789",
        )

        self.assertEqual(order.source_platform, "shopify")
        self.assertEqual(order.shopify_order_id, "SHOP123456789")
        self.assertFalse(order.ebay_order_id)

        ebay_order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            source_platform="ebay",
            ebay_order_id="12-34567-89012",
        )

        self.assertEqual(ebay_order.source_platform, "ebay")
        self.assertEqual(ebay_order.ebay_order_id, "12-34567-89012")
        self.assertFalse(ebay_order.shopify_order_id)

        manual_order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            source_platform="manual",
        )
        self.assertEqual(manual_order.source_platform, "manual")

        order_no_platform = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            source_platform=False,
        )
        self.assertFalse(order_no_platform.source_platform)

    def test_copy_method(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            source_platform="shopify",
            shopify_order_id="SHOP123",
            ebay_order_id="EBAY456",
            shipstation_order_id="SHIP789",
            shipping_charge=20.0,
            shipping_paid=15.0,
        )

        SaleOrderLineFactory.create(
            self.env,
            order_id=order.id,
            product_id=self.product.id,
            product_uom_qty=1,
        )

        copied_order = order.copy()

        self.assertFalse(copied_order.shopify_order_id)
        self.assertFalse(copied_order.ebay_order_id)
        self.assertFalse(copied_order.shipstation_order_id)

        self.assertEqual(copied_order.source_platform, "shopify")
        self.assertEqual(copied_order.shipping_charge, 20.0)
        self.assertEqual(copied_order.shipping_paid, 15.0)

    def test_shopify_note_field(self) -> None:
        test_note = "Payment: PayPal\nOrder Notes: Rush delivery\neBay Item: 123456"

        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            shopify_note=test_note,
        )

        self.assertEqual(order.shopify_note, test_note)

        order.note = "Internal note for warehouse"
        self.assertEqual(order.shopify_note, test_note)
        self.assertIn("Internal note for warehouse", str(order.note))

    def test_shipping_tracking_numbers(self) -> None:
        tracking_data = "UPS: 1Z999AA10123456784\nUSPS: 9400100000000000000000"

        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            carrier_id=self.carrier.id,
            shipping_tracking_numbers=tracking_data,
        )

        self.assertEqual(order.shipping_tracking_numbers, tracking_data)
        self.assertIn("1Z999AA10123456784", order.shipping_tracking_numbers)
        self.assertIn("9400100000000000000000", order.shipping_tracking_numbers)

    def test_shipping_fields_in_different_states(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            shipping_charge=30.0,
            shipping_paid=25.0,
        )

        SaleOrderLineFactory.create(
            self.env,
            order_id=order.id,
            product_id=self.product.id,
            product_uom_qty=1,
            price_unit=100.0,
        )

        self.assertEqual(order.state, "draft")
        self.assertEqual(order.shipping_margin, 5.0)

        order.action_confirm()
        self.assertEqual(order.state, "sale")

        order.shipping_paid = 20.0
        self.assertEqual(order.shipping_margin, 10.0)

        order._create_invoices()
        invoice = order.invoice_ids[0]
        invoice.action_post()

        order.shipping_charge = 35.0
        self.assertEqual(order.shipping_margin, 15.0)

    def test_shipping_with_multiple_currencies(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            shipping_charge=100.0,
            shipping_paid=80.0,
        )

        self.assertEqual(order.shipping_margin, 20.0)

        self.assertEqual(order.shipping_charge, 100.0)
        self.assertEqual(order.shipping_paid, 80.0)

        self.assertTrue(order.currency_id)

    def test_delivery_carrier_service_map_normalization(self) -> None:
        service_map = self.env["delivery.carrier.service.map"]

        test_cases = [
            ("UPS Ground", "ups ground"),
            ("UPS® Ground™", "ups ground"),
            ("USPS Priority Mail®", "usps priority mail"),
            ("Free Shipping!", "free shipping"),
            ("Via standard shipping", "via standard shipping"),
            ("  Shipping  ", "shipping"),
            ("", ""),
            (None, ""),
        ]

        for input_name, expected in test_cases:
            result = service_map.normalize_service_name(input_name)
            self.assertEqual(result, expected, f"Failed for input: {input_name}")

    def test_delivery_carrier_mapping_lookup(self) -> None:
        ups_carrier = self.env["delivery.carrier"].search([("name", "=", "UPS Ground")], limit=1)
        self.assertTrue(ups_carrier, "UPS Ground carrier should exist")

        mapping = self.env["delivery.carrier.service.map"].search(
            [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", "ups ground")], limit=1
        )

        self.assertTrue(mapping, "UPS Ground mapping should exist")
        self.assertEqual(mapping.carrier.id, ups_carrier.id)

    def test_all_common_shipping_methods_mapped(self) -> None:
        common_methods = [
            ("Standard Shipping", "standard shipping"),
            ("UPS Ground", "ups ground"),
            ("USPS Ground Advantage", "usps ground advantage"),
            ("USPS Priority Mail", "usps priority mail"),
            ("Standard Shipping (eBay GSP)", "standard shipping ebay gsp"),
            ("Via standard shipping", "via standard shipping"),
            ("Flat Rate Freight", "flat rate freight"),
            ("Warehouse", "warehouse"),
            ("Free Shipping", "free shipping"),
            ("Local Pickup", "local pickup"),
        ]

        service_map = self.env["delivery.carrier.service.map"]

        for original, normalized in common_methods:
            mapping = service_map.search(
                [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", normalized)], limit=1
            )

            self.assertTrue(mapping, f"No mapping found for '{original}' (normalized: '{normalized}')")
            self.assertTrue(mapping.carrier, f"Mapping for '{original}' has no carrier")

    def test_unknown_shipping_method_handling(self) -> None:
        from ...services.shopify.sync.importers.order_importer import OrderImporter

        sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_orders")

        OrderImporter(self.env, sync_record)

        SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            currency_id=self.usd_currency.id,
        )

        service_map = self.env["delivery.carrier.service.map"]
        unknown_normalized = service_map.normalize_service_name("Unknown Carrier Express")

        existing_mapping = service_map.search(
            [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", unknown_normalized)]
        )
        self.assertFalse(existing_mapping, "This test requires 'Unknown Carrier Express' to be unmapped")

    def test_shipping_charge_capture(self) -> None:
        order = SaleOrderFactory.create(
            self.env,
            partner_id=self.partner.id,
            currency_id=self.usd_currency.id,
        )

        SaleOrderLineFactory.create(
            self.env,
            order_id=order.id,
            product_id=self.product.id,
            product_uom_qty=1,
            price_unit=100.0,
        )

        ups_carrier = self.env["delivery.carrier"].search([("name", "=", "UPS Ground")], limit=1)
        self.assertTrue(ups_carrier)

        delivery_line = SaleOrderLineFactory.create(
            self.env,
            order_id=order.id,
            product_id=ups_carrier.product_id.id,
            product_uom_qty=1,
            price_unit=15.99,
            is_delivery=True,
        )

        order.carrier_id = ups_carrier.id
        order.shipping_charge = 15.99

        self.assertEqual(order.shipping_charge, 15.99)
        self.assertEqual(delivery_line.price_unit, 15.99)

    def test_multiple_platform_mappings(self) -> None:
        standard_carrier = self.env["delivery.carrier"].search([("name", "=", "Standard Shipping")], limit=1)
        self.assertTrue(standard_carrier)

        variations = [
            "standard shipping",
            "via standard shipping",
            "shipping",
        ]

        for normalized_name in variations:
            mapping = self.env["delivery.carrier.service.map"].search(
                [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", normalized_name)], limit=1
            )

            self.assertTrue(mapping, f"No mapping for variation: {normalized_name}")
            self.assertEqual(
                mapping.carrier.id, standard_carrier.id, f"Variation '{normalized_name}' doesn't map to Standard Shipping"
            )

    def test_freight_variations_mapped(self) -> None:
        mappings = self.env["delivery.carrier.service.map"].search(
            [
                ("platform", "=", "shopify"),
                (
                    "platform_service_normalized_name",
                    "in",
                    [
                        "freight",
                        "freight shipping",
                        "freight shipment",
                        "flat rate freight",
                        "freight commercial address",
                        "freight commercial address or local freight hub",
                    ],
                ),
            ]
        )

        self.assertEqual(len(mappings), 6, "All freight variations should be mapped")

        carriers = mappings.mapped("carrier")
        self.assertGreaterEqual(len(carriers), 2, "Freight should map to multiple carriers")

    def test_customer_arranged_variations(self) -> None:
        customer_carrier = self.env["delivery.carrier"].search([("name", "=", "Customer Arranged Shipping")], limit=1)
        self.assertTrue(customer_carrier)

        variations = [
            "customer arranged shipping",
            "customer to arrange shipping",
            "buyer to arrange shipping",
            "buyer to provide label for shipment",
            "buyer to prove dhl label",
        ]

        for normalized_name in variations:
            mapping = self.env["delivery.carrier.service.map"].search(
                [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", normalized_name)], limit=1
            )

            self.assertTrue(mapping, f"No mapping for: {normalized_name}")
            self.assertEqual(mapping.carrier.id, customer_carrier.id)
