from ..common_imports import tagged, datetime, timedelta, INTEGRATION_TAGS
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import PartnerFactory, ProductFactory


@tagged(*INTEGRATION_TAGS)
class TestShippingAnalytics(IntegrationTestCase):
    """Comprehensive test suite for shipping analytics functionality

    This test class covers:
    - Shipping analytics data calculations
    - Platform-specific analytics
    - Margin analysis and reporting
    - Integration with existing orders
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._create_test_data()

    @classmethod
    def _get_default_order_vals(cls) -> dict:
        return {
            "tag_ids": [(4, cls.test_order_tag.id)],
        }

    @classmethod
    def _create_test_data(cls) -> None:
        from ..fixtures.factories import CrmTagFactory

        cls.test_order_tag = CrmTagFactory.create(
            cls.env,
            name="Test Suite Data",
            color=10,
        )
        cls.partner_shopify = PartnerFactory.create(
            cls.env,
            name="Shopify Analytics Customer",
            email="shopify.analytics@test.com",
        )

        cls.partner_ebay = PartnerFactory.create(
            cls.env,
            name="eBay Analytics Customer",
            email="ebay.analytics@test.com",
        )

        cls.partner_manual = PartnerFactory.create(
            cls.env,
            name="Manual Analytics Customer",
            email="manual.analytics@test.com",
        )

        cls.product = ProductFactory.create(
            cls.env,
            list_price=200.0,
            standard_price=100.0,
        ).product_variant_id

        delivery_products = {}
        for carrier_name in ["UPS", "USPS", "FedEx"]:
            delivery_products[carrier_name] = cls.env["product.product"].create(
                {
                    "name": f"Test {carrier_name} Delivery",
                    "type": "service",
                    "list_price": 0.0,
                }
            )

        cls.carrier_ups = cls.env["delivery.carrier"].create(
            {
                "name": "Test UPS",
                "delivery_type": "fixed",
                "fixed_price": 15.0,
                "product_id": delivery_products["UPS"].id,
            }
        )

        cls.carrier_usps = cls.env["delivery.carrier"].create(
            {
                "name": "Test USPS",
                "delivery_type": "fixed",
                "fixed_price": 10.0,
                "product_id": delivery_products["USPS"].id,
            }
        )

        cls.carrier_fedex = cls.env["delivery.carrier"].create(
            {
                "name": "Test FedEx",
                "delivery_type": "fixed",
                "fixed_price": 20.0,
                "product_id": delivery_products["FedEx"].id,
            }
        )

        cls._create_test_orders()

    @classmethod
    def _create_test_orders(cls) -> None:
        default_order_vals = cls._get_default_order_vals()

        for i in range(3):
            order = cls.env["sale.order"].create(
                {
                    **default_order_vals,
                    "partner_id": cls.partner_shopify.id,
                    "source_platform": "shopify",
                    "shopify_order_id": f"SHOP-ANALYTICS-{i}",
                    "carrier_id": cls.carrier_ups.id,
                    "shipping_charge": 25.0,
                    "shipping_paid": 20.0 - i,  # Varying margins
                    "date_order": datetime.now() - timedelta(days=i),
                }
            )
            cls._add_order_line(order)
            order.action_confirm()

        for i in range(3):
            order = cls.env["sale.order"].create(
                {
                    **default_order_vals,
                    "partner_id": cls.partner_ebay.id,
                    "source_platform": "ebay",
                    "ebay_order_id": f"EBAY-ANALYTICS-{i}",
                    "carrier_id": cls.carrier_usps.id,
                    "shipping_charge": 15.0,
                    "shipping_paid": 20.0 - (i * 10),  # Some negative margins
                    "date_order": datetime.now() - timedelta(days=i + 3),
                }
            )
            cls._add_order_line(order)
            order.action_confirm()

        order = cls.env["sale.order"].create(
            {
                **default_order_vals,
                "partner_id": cls.partner_manual.id,
                "source_platform": "manual",
                "carrier_id": cls.carrier_fedex.id,
                "shipping_charge": 30.0,
                "shipping_paid": 25.0,
                "date_order": datetime.now() - timedelta(days=7),
            }
        )
        cls._add_order_line(order)

    @classmethod
    def _add_order_line(cls, order: "odoo.model.sale_order") -> None:
        cls.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": cls.product.id,
                "product_uom_qty": 2,
                "price_unit": 200.0,
            }
        )

    def test_shipping_margin_analytics(self) -> None:
        orders = self.env["sale.order"].search([("tag_ids", "in", [self.test_order_tag.id])])

        for order in orders:
            expected_margin = order.shipping_charge - order.shipping_paid
            self.assertEqual(order.shipping_margin, expected_margin, f"Order {order.name} margin calculation incorrect")

    def test_platform_analytics_grouping(self) -> None:
        platform_data = {}

        for platform in ["shopify", "ebay", "manual"]:
            orders = self.env["sale.order"].search(
                [
                    ("source_platform", "=", platform),
                    ("tag_ids", "in", [self.test_order_tag.id]),
                ]
            )

            platform_data[platform] = {
                "count": len(orders),
                "total_charge": sum(orders.mapped("shipping_charge")),
                "total_paid": sum(orders.mapped("shipping_paid")),
                "total_margin": sum(orders.mapped("shipping_margin")),
            }

        self.assertEqual(platform_data["shopify"]["count"], 3)
        self.assertEqual(platform_data["shopify"]["total_charge"], 75.0)  # 25 * 3
        self.assertEqual(platform_data["shopify"]["total_paid"], 57.0)  # 20 + 19 + 18
        self.assertEqual(platform_data["shopify"]["total_margin"], 18.0)  # 5 + 6 + 7

        self.assertEqual(platform_data["ebay"]["count"], 3)
        self.assertEqual(platform_data["ebay"]["total_charge"], 45.0)  # 15 * 3
        self.assertEqual(platform_data["ebay"]["total_paid"], 30.0)  # 20 + 10 + 0
        self.assertEqual(platform_data["ebay"]["total_margin"], 15.0)  # -5 + 5 + 15

        self.assertEqual(platform_data["manual"]["count"], 1)
        self.assertEqual(platform_data["manual"]["total_charge"], 30.0)
        self.assertEqual(platform_data["manual"]["total_paid"], 25.0)
        self.assertEqual(platform_data["manual"]["total_margin"], 5.0)

    def test_carrier_analytics(self) -> None:
        ups_orders = self.env["sale.order"].search(
            [("carrier_id", "=", self.carrier_ups.id), ("tag_ids", "in", [self.test_order_tag.id])]
        )

        usps_orders = self.env["sale.order"].search(
            [("carrier_id", "=", self.carrier_usps.id), ("tag_ids", "in", [self.test_order_tag.id])]
        )

        fedex_orders = self.env["sale.order"].search(
            [("carrier_id", "=", self.carrier_fedex.id), ("tag_ids", "in", [self.test_order_tag.id])]
        )

        self.assertEqual(len(ups_orders), 3)
        self.assertEqual(len(usps_orders), 3)
        self.assertEqual(len(fedex_orders), 1)

        ups_avg_margin = sum(ups_orders.mapped("shipping_margin")) / len(ups_orders)
        self.assertEqual(ups_avg_margin, 6.0)  # (5 + 6 + 7) / 3

        usps_avg_margin = sum(usps_orders.mapped("shipping_margin")) / len(usps_orders)
        self.assertEqual(usps_avg_margin, 5.0)  # (-5 + 5 + 15) / 3

    def test_negative_margin_detection(self) -> None:
        negative_margin_orders = self.env["sale.order"].search(
            [
                ("shipping_margin", "<", 0),
                ("tag_ids", "in", [self.test_order_tag.id]),
            ]
        )

        self.assertEqual(len(negative_margin_orders), 1)
        self.assertEqual(negative_margin_orders.source_platform, "ebay")
        self.assertEqual(negative_margin_orders.shipping_margin, -5.0)

    def test_date_range_analytics(self) -> None:
        all_test_orders = self.env["sale.order"].search(
            [
                ("tag_ids", "in", [self.test_order_tag.id]),
                ("carrier_id", "!=", False),
            ]
        )

        by_platform = {}
        for order in all_test_orders:
            platform = order.source_platform or "none"
            if platform not in by_platform:
                by_platform[platform] = []
            by_platform[platform].append(order)

        self.assertIn("shopify", by_platform, "Should have Shopify orders")
        self.assertIn("ebay", by_platform, "Should have eBay orders")
        self.assertGreaterEqual(len(all_test_orders), 6, "Should have at least 6 test orders")

        now = datetime.now()
        three_days_ago = now - timedelta(days=3)

        recent_orders = all_test_orders.filtered(lambda o: o.date_order and o.date_order >= three_days_ago)
        older_orders = all_test_orders.filtered(lambda o: o.date_order and o.date_order < three_days_ago)

        self.assertGreater(len(recent_orders), 0, "Should have some recent orders")
        self.assertGreater(len(older_orders), 0, "Should have some older orders")

        for order in recent_orders:
            self.assertGreaterEqual(order.date_order, three_days_ago, "Recent orders should be within last 3 days")

        for order in older_orders:
            self.assertLess(order.date_order, three_days_ago, "Older orders should be more than 3 days old")

    def test_shipping_efficiency_metrics(self) -> None:
        all_orders = self.env["sale.order"].search([("tag_ids", "in", [self.test_order_tag.id])])

        total_charge = sum(all_orders.mapped("shipping_charge"))
        total_paid = sum(all_orders.mapped("shipping_paid"))
        total_margin = sum(all_orders.mapped("shipping_margin"))

        efficiency = (total_margin / total_charge) * 100 if total_charge else 0

        self.assertEqual(total_charge, 150.0)  # 75 + 45 + 30
        self.assertEqual(total_paid, 112.0)  # 57 + 30 + 25
        self.assertEqual(total_margin, 38.0)  # 18 + 15 + 5
        self.assertAlmostEqual(efficiency, 25.33, places=2)

    def test_analytics_with_no_shipping_data(self) -> None:
        no_shipping_order = self.env["sale.order"].create(
            {
                **self._get_default_order_vals(),
                "partner_id": self.partner_manual.id,
                "source_platform": "manual",
            }
        )

        self._add_order_line(no_shipping_order)

        self.assertEqual(no_shipping_order.shipping_charge, 0.0)
        self.assertEqual(no_shipping_order.shipping_paid, 0.0)
        self.assertEqual(no_shipping_order.shipping_margin, 0.0)

        all_margins = (
            self.env["sale.order"]
            .search([("tag_ids", "in", [self.test_order_tag.id]), ("partner_id", "=", self.partner_manual.id)])
            .mapped("shipping_margin")
        )

        self.assertIn(0.0, all_margins)
        self.assertEqual(len(all_margins), 2)  # Original + new order
