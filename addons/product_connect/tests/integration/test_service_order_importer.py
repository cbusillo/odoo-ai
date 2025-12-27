from ..common_imports import logging, Decimal, patch, MagicMock, tagged, INTEGRATION_TAGS

from ...services.shopify.gql import (
    OrderFields,
    CurrencyCode,
)
from ...services.shopify.gql.fragments import (
    OrderFieldsFulfillments,
    OrderFieldsFulfillmentsTrackingInfo,
    MoneyBagFields,
    MoneyBagFieldsPresentmentMoney,
    MoneyBagFieldsShopMoney,
    OrderLineItemFields,
    OrderLineItemFieldsVariant,
    OrderLineItemFieldsOriginalUnitPriceSet,
    OrderLineItemFieldsDiscountAllocations,
    OrderLineItemFieldsDiscountAllocationsAllocatedAmountSet,
)
from ...services.shopify.sync.importers.order_importer import OrderImporter, EbayOrderData
from ...services.shopify.sync.importers.customer_importer import CustomerImporter
from ...services.shopify.helpers import ShopifyDataError

from ..fixtures.shopify_responses import (
    create_shopify_order_response,
    create_shopify_customer_response,
    create_shopify_address_response,
    create_shopify_order_line_item_response,
    create_shopify_shipping_line_response,
    create_money_bag,
)
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ShopifySyncFactory, PartnerFactory

_logger = logging.getLogger(__name__)


@tagged(*INTEGRATION_TAGS)
class TestOrderImporter(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()  # Set up Shopify API mocks
        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_orders")
        self.importer = OrderImporter(self.env, self.sync_record)

        self.usd_currency = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        if not self.usd_currency:
            self.usd_currency = self.env["res.currency"].create({"name": "USD", "symbol": "$", "rate": 1.0})

        import time

        base = int(time.time()) % 10000
        sku_a = str(50000 + base)  # 5xxxx series
        sku_b = str(60000 + base)  # 6xxxx series

        self.product_a = self.env["product.product"].create(
            {
                "name": "Product A",
                "default_code": sku_a,
                "shopify_variant_id": "987654321",
                "list_price": 99.99,
                "type": "consu",
            }
        )

        self.product_b = self.env["product.product"].create(
            {
                "name": "Product B",
                "default_code": sku_b,
                "shopify_variant_id": "987654322",
                "list_price": 49.99,
                "type": "consu",
            }
        )

        self.customer_partner = PartnerFactory.create(
            self.env,
            name="Test Customer",
            email="test@example.com",
            shopify_customer_id="123456789",
        )

        self.ups_carrier = self.env["delivery.carrier"].create(
            {
                "name": "UPS Ground",
                "product_id": self.env["product.product"]
                .create(
                    {
                        "name": "UPS Ground Delivery",
                        "type": "consu",
                        "list_price": 10.0,
                    }
                )
                .id,
                "delivery_type": "fixed",
                "fixed_price": 10.0,
            }
        )

        existing_map = self.env["delivery.carrier.service.map"].search(
            [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", "ups ground")], limit=1
        )

        if not existing_map:
            self.env["delivery.carrier.service.map"].create(
                {
                    "platform": "shopify",
                    "platform_service_normalized_name": "ups ground",
                    "carrier": self.ups_carrier.id,
                }
            )

    def _import_order_and_verify_success(self, shopify_order: OrderFields) -> "odoo.model.sale_order":
        result = self.importer._import_one(shopify_order)
        self.assertTrue(result)
        shopify_id = shopify_order.id.split("/")[-1]
        order = self.env["sale.order"].search([("shopify_order_id", "=", shopify_id)])
        self.assertTrue(order)
        return order

    def _mock_fetch_page_and_import(self, shopify_order: OrderFields) -> int:
        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_page = MagicMock()
            mock_page.nodes = [shopify_order]
            mock_page.page_info.has_next_page = False
            mock_page.page_info.end_cursor = None

            mock_fetch.return_value = mock_page
            return self.importer.import_orders_since_last_import()

    def _mock_fetch_page_with_error(
        self, order_data: dict[str, object] | None, expected_exception: type[Exception] | Exception
    ) -> None:
        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            if order_data:
                order = OrderFields(**order_data)

                mock_page = MagicMock()
                mock_page.nodes = [order]
                mock_page.page_info.has_next_page = False
                mock_page.page_info.end_cursor = None

                mock_fetch.return_value = mock_page
            else:
                mock_fetch.side_effect = expected_exception

            exception_type = expected_exception if isinstance(expected_exception, type) else type(expected_exception)
            with self.assertRaises(exception_type):
                self.importer.import_orders_since_last_import()

    def test_normalise_carrier_name(self) -> None:
        test_cases = [
            ("UPS Ground", "ups ground"),
            ("UPS® Ground™", "ups ground"),
            ("FedEx - Express", "fedex express"),
            ("DHL (Express)", "dhl express"),
            ("USPS Priority Mail®", "usps priority mail"),
            ("", ""),
            (None, ""),
        ]

        service_map_model = self.env["delivery.carrier.service.map"]
        for input_name, expected in test_cases:
            result = service_map_model.normalize_service_name(input_name)
            self.assertEqual(result, expected, f"Failed for input: {input_name}")

    def test_get_amount_for_order_currency(self) -> None:
        usd_money_bag = MoneyBagFields(
            presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("50.00"), currencyCode=CurrencyCode.CAD),
            shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("40.00"), currencyCode=CurrencyCode.USD),
        )
        result = OrderImporter._get_amount_for_order_currency(usd_money_bag, CurrencyCode.USD)
        self.assertEqual(result, Decimal("40.00"))

        cad_money_bag = MoneyBagFields(
            presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("50.00"), currencyCode=CurrencyCode.CAD),
            shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("40.00"), currencyCode=CurrencyCode.USD),
        )
        result = OrderImporter._get_amount_for_order_currency(cad_money_bag, CurrencyCode.CAD)
        self.assertEqual(result, Decimal("50.00"))

        no_shop_money_bag = MoneyBagFields(
            presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("50.00"), currencyCode=CurrencyCode.USD),
            shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("0.00"), currencyCode=CurrencyCode.USD),
        )
        result = OrderImporter._get_amount_for_order_currency(no_shop_money_bag, CurrencyCode.USD)
        self.assertEqual(result, Decimal("50.00"))

        result = OrderImporter._get_amount_for_order_currency(None, CurrencyCode.USD)  # type: ignore[arg-type]
        self.assertEqual(result, Decimal("0"))

    def test_get_discount_allocation_amount(self) -> None:
        line = OrderLineItemFields(
            id="gid://shopify/LineItem/123",
            sku="TEST",
            quantity=2,
            name="Test Product",
            variant=OrderLineItemFieldsVariant(id="gid://shopify/ProductVariant/123"),
            originalUnitPriceSet=OrderLineItemFieldsOriginalUnitPriceSet(
                presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("100.00"), currencyCode=CurrencyCode.USD),
                shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("100.00"), currencyCode=CurrencyCode.USD),
            ),
            customAttributes=[],
            discountAllocations=[
                OrderLineItemFieldsDiscountAllocations(
                    allocated_amount_set=OrderLineItemFieldsDiscountAllocationsAllocatedAmountSet(
                        presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("10.00"), currencyCode=CurrencyCode.USD),
                        shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("10.00"), currencyCode=CurrencyCode.USD),
                    )
                ),
                OrderLineItemFieldsDiscountAllocations(
                    allocated_amount_set=OrderLineItemFieldsDiscountAllocationsAllocatedAmountSet(
                        presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("5.00"), currencyCode=CurrencyCode.USD),
                        shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("5.00"), currencyCode=CurrencyCode.USD),
                    )
                ),
            ],
        )

        result = OrderImporter._get_discount_allocation_amount(line, CurrencyCode.USD)
        self.assertEqual(result, Decimal("15.00"))

        line_no_discounts = OrderLineItemFields(
            id="gid://shopify/LineItem/124",
            sku="TEST2",
            quantity=1,
            name="Test Product 2",
            variant=OrderLineItemFieldsVariant(id="gid://shopify/ProductVariant/124"),
            originalUnitPriceSet=OrderLineItemFieldsOriginalUnitPriceSet(
                presentmentMoney=MoneyBagFieldsPresentmentMoney(amount=Decimal("50.00"), currencyCode=CurrencyCode.USD),
                shopMoney=MoneyBagFieldsShopMoney(amount=Decimal("50.00"), currencyCode=CurrencyCode.USD),
            ),
            customAttributes=[],
            discountAllocations=[],
        )

        result = OrderImporter._get_discount_allocation_amount(line_no_discounts, CurrencyCode.USD)
        self.assertEqual(result, Decimal("0"))

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_basic(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/111",
            customer=create_shopify_customer_response(),
            shipping_address=create_shopify_address_response(address1="123 Shipping St"),
            billing_address=create_shopify_address_response(address1="456 Billing Ave"),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code, quantity=2)],
            shipping_lines=[create_shopify_shipping_line_response(title="UPS Ground")],
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)
        mock_import_customer.assert_called_once()

        order = self.env["sale.order"].search([("shopify_order_id", "=", "111")])
        self.assertTrue(order)
        self.assertEqual(order.name, "#1001")
        self.assertEqual(order.partner_id.id, self.customer_partner.id)
        self.assertEqual(order.currency_id.id, self.usd_currency.id)
        self.assertEqual(order.state, "sale")

        product_lines = order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines[0].product_id.id, self.product_a.id)
        self.assertEqual(product_lines[0].product_uom_qty, 2)
        self.assertEqual(product_lines[0].price_unit, 99.99)

        delivery_lines = order.order_line.filtered("is_delivery")
        self.assertEqual(len(delivery_lines), 1)
        self.assertEqual(delivery_lines[0].price_unit, 10.0)

    def test_import_order_no_customer(self) -> None:
        order_data = create_shopify_order_response()
        shopify_order = OrderFields(**order_data)

        result = self.importer._import_one(shopify_order)
        self.assertFalse(result)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_customer_not_found(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(customer=create_shopify_customer_response(gid="gid://shopify/Customer/999999"))
        shopify_order = OrderFields(**order_data)

        result = self.importer._import_one(shopify_order)
        self.assertFalse(result)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_unsupported_currency(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            currency_code="XXX",
            customer=create_shopify_customer_response(),
        )
        shopify_order = OrderFields(**order_data)

        with self.assertRaises(ShopifyDataError) as cm:
            self.importer._import_one(shopify_order)
        self.assertIn("Unsupported currency", str(cm.exception))

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_discounts(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.product_a.default_code,
                    discount_allocations=[{"allocatedAmountSet": create_money_bag("10.00")}],
                )
            ],
            discount_applications=[
                {
                    "__typename": "DiscountCodeApplication",
                    "code": "SUMMER10",
                    "title": "Summer Sale",
                }
            ],
            totalDiscountsSet=create_money_bag("10.00"),
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        self.assertTrue(order)

        product_lines = order.order_line.filtered(lambda l: not l.is_delivery and l.product_id.id == self.product_a.id)
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines[0].price_unit, 89.99)

        discount_lines = order.order_line.filtered(lambda l: l.product_id.default_code == "DISC")
        self.assertEqual(len(discount_lines), 1)
        self.assertEqual(discount_lines[0].price_unit, -10.0)
        self.assertEqual(discount_lines[0].name, "SUMMER10")

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_taxes(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        tax_lines = [
            {
                "title": "State Tax",
                "ratePercentage": 0.08,
                "priceSet": create_money_bag("8.00"),
            },
            {
                "title": "County Tax",
                "ratePercentage": 0.02,
                "priceSet": create_money_bag("2.00"),
            },
        ]

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
            tax_lines=tax_lines,
        )

        order = self._import_order_and_verify_success(OrderFields(**order_data))
        tax_lines = order.order_line.filtered(lambda l: l.product_id.default_code == "TAX")
        self.assertEqual(len(tax_lines), 2)

        state_tax = tax_lines.filtered(lambda l: l.name == "State Tax")
        self.assertEqual(state_tax.price_unit, 8.0)

        county_tax = tax_lines.filtered(lambda l: l.name == "County Tax")
        self.assertEqual(county_tax.price_unit, 2.0)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_tracking(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        fulfillments = [
            OrderFieldsFulfillments(
                trackingInfo=[
                    OrderFieldsFulfillmentsTrackingInfo(number="1Z123456789", url=None, company="UPS"),
                    OrderFieldsFulfillmentsTrackingInfo(number="1Z987654321", url=None, company="UPS"),
                ]
            )
        ]

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
            fulfillments=fulfillments,
        )

        order = self._import_order_and_verify_success(OrderFields(**order_data))

        self.env["stock.picking"].create(
            {
                "partner_id": order.partner_id.id,
                "picking_type_id": self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1).id,
                "location_id": self.env["stock.location"].search([("usage", "=", "internal")], limit=1).id,
                "location_dest_id": self.env["stock.location"].search([("usage", "=", "customer")], limit=1).id,
                "origin": order.name,
                "sale_id": order.id,
            }
        )

        shopify_order = OrderFields(**order_data)
        self.importer._import_one(shopify_order)

        picking = order.picking_ids[0]
        self.assertEqual(picking.carrier_tracking_ref, "1Z123456789, 1Z987654321")

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_update_existing(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        existing_order = self.env["sale.order"].create(
            {
                "shopify_order_id": "111",
                "name": "#1001",
                "partner_id": self.customer_partner.id,
                "currency_id": self.usd_currency.id,
            }
        )

        self.env["sale.order.line"].create(
            {
                "order_id": existing_order.id,
                "product_id": self.product_a.id,
                "product_uom_qty": 1,
                "price_unit": 89.99,
                "shopify_order_line_id": "1",
            }
        )

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/111",
            name="#1001-UPDATED",
            customer=create_shopify_customer_response(),
            line_items=[
                create_shopify_order_line_item_response(
                    gid="gid://shopify/LineItem/1",
                    sku=self.product_a.default_code,
                    quantity=2,
                ),
                create_shopify_order_line_item_response(
                    gid="gid://shopify/LineItem/2",
                    sku=self.product_b.default_code,
                    unit_price="49.99",
                    variant_id="gid://shopify/ProductVariant/987654322",
                ),
            ],
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)

        existing_order.invalidate_recordset()
        self.assertEqual(existing_order.name, "#1001-UPDATED")

        lines = existing_order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(lines), 2)

        line_a = lines.filtered(lambda l: l.product_id.id == self.product_a.id)
        self.assertEqual(line_a.product_uom_qty, 2)
        self.assertEqual(line_a.price_unit, 99.99)

        line_b = lines.filtered(lambda l: l.product_id.id == self.product_b.id)
        self.assertEqual(line_b.product_uom_qty, 1)
        self.assertEqual(line_b.price_unit, 49.99)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_missing_product(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[
                create_shopify_order_line_item_response(sku="999999", variant_id="gid://shopify/ProductVariant/999999"),
                create_shopify_order_line_item_response(sku=self.product_a.default_code),
            ],
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        self.assertTrue(order)

        product_lines = order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines[0].product_id.id, self.product_a.id)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_unknown_carrier(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
            shipping_lines=[create_shopify_shipping_line_response(title="Unknown Carrier", price="15.00")],
        )

        shopify_order = OrderFields(**order_data)

        with self.assertRaises(ShopifyDataError) as cm:
            self.importer._import_one(shopify_order)
        self.assertIn("Unknown delivery service", str(cm.exception))

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_sku_with_bin_location(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code + " - Bin A1")],
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        product_lines = order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines[0].product_id.id, self.product_a.id)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_multiple_shipping_carriers(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        existing_fedex_map = self.env["delivery.carrier.service.map"].search(
            [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", "fedex express")], limit=1
        )

        if not existing_fedex_map:
            fedex_carrier = self.env["delivery.carrier"].create(
                {
                    "name": "FedEx Express",
                    "product_id": self.env["product.product"]
                    .create(
                        {
                            "name": "FedEx Express Delivery",
                            "type": "consu",
                            "list_price": 20.0,
                        }
                    )
                    .id,
                    "delivery_type": "fixed",
                    "fixed_price": 20.0,
                }
            )

            self.env["delivery.carrier.service.map"].create(
                {
                    "platform": "shopify",
                    "platform_service_normalized_name": "fedex express",
                    "carrier": fedex_carrier.id,
                }
            )

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
            shipping_lines=[
                create_shopify_shipping_line_response(title="UPS Ground"),
                create_shopify_shipping_line_response(title="FedEx Express", price="20.00"),
            ],
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        delivery_lines = order.order_line.filtered("is_delivery")
        self.assertEqual(len(delivery_lines), 2)

        total_shipping = sum(line.price_unit for line in delivery_lines)
        self.assertEqual(total_shipping, 30.0)

        self.assertEqual(order.carrier_id.name, "UPS Ground")

    def test_extract_tracking_numbers(self) -> None:
        fulfillments = [
            OrderFieldsFulfillments(
                trackingInfo=[
                    OrderFieldsFulfillmentsTrackingInfo(number="  1Z123456789  ", url=None, company="UPS"),
                    OrderFieldsFulfillmentsTrackingInfo(number="1Z987654321", url=None, company="UPS"),
                    OrderFieldsFulfillmentsTrackingInfo(number="1Z123456789", url=None, company="UPS"),  # duplicate
                    OrderFieldsFulfillmentsTrackingInfo(number="", url=None, company="UPS"),  # empty
                    OrderFieldsFulfillmentsTrackingInfo(number=None, url=None, company="UPS"),  # None
                ]
            ),
            OrderFieldsFulfillments(
                trackingInfo=[OrderFieldsFulfillmentsTrackingInfo(number="FEDEX123", url=None, company="FedEx")]
            ),
        ]

        order_data = create_shopify_order_response(fulfillments=fulfillments)
        shopify_order = OrderFields(**order_data)

        numbers = self.importer._extract_tracking_numbers(shopify_order)
        self.assertEqual(numbers, ["1Z123456789", "1Z987654321", "FEDEX123"])

    def test_parse_ebay_note_attributes(self) -> None:
        complete_note = """eBay Sales Record Number: 21478
eBay Order Id: 14-13240-64196
eBay Earliest Delivery Date: 2025-06-27T07:00:00.000Z
eBay Latest Delivery Date: 2025-06-30T07:00:00.000Z
eBay Handle By Date: 2025-06-27T03:59:59.000Z
eBay Account: outboardpartswarehouseva"""

        result = EbayOrderData.from_note_attributes(complete_note)
        self.assertEqual(result.sales_record, "21478")
        self.assertEqual(result.order_id, "14-13240-64196")
        self.assertEqual(result.latest_delivery_date.isoformat(), "2025-06-30T07:00:00")
        self.assertEqual(result.earliest_delivery_date.isoformat(), "2025-06-27T07:00:00")
        self.assertIsNone(result.latest_delivery_date.tzinfo)
        self.assertIsNone(result.earliest_delivery_date.tzinfo)

        partial_note = """eBay Sales Record Number: 12345
eBay Order Id: 22-33333-44444"""

        result = EbayOrderData.from_note_attributes(partial_note)
        self.assertEqual(result.sales_record, "12345")
        self.assertEqual(result.order_id, "22-33333-44444")
        self.assertIsNone(result.latest_delivery_date)
        self.assertIsNone(result.earliest_delivery_date)

        bad_date_note = """eBay Sales Record Number: 99999
eBay Latest Delivery Date: invalid-date
eBay Earliest Delivery Date: 2025-13-45"""

        result = EbayOrderData.from_note_attributes(bad_date_note)
        self.assertEqual(result.sales_record, "99999")
        self.assertIsNone(result.latest_delivery_date)
        self.assertIsNone(result.earliest_delivery_date)

        result = EbayOrderData.from_note_attributes("")
        self.assertIsNone(result.sales_record)
        self.assertIsNone(result.order_id)
        self.assertIsNone(result.latest_delivery_date)
        self.assertIsNone(result.earliest_delivery_date)

        whitespace_note = """eBay Sales Record Number:    54321   
eBay Order Id:   11-22222-33333   """

        result = EbayOrderData.from_note_attributes(whitespace_note)
        self.assertEqual(result.sales_record, "54321")
        self.assertEqual(result.order_id, "11-22222-33333")

    @patch.object(CustomerImporter, "import_customer")
    @patch.object(CustomerImporter, "process_address")
    def test_resolve_address_creates_new(self, mock_process_address: MagicMock, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True
        mock_process_address.return_value = True

        shipping_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/999", name="Jane Doe", address1="789 New St"
        )

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            shipping_address=shipping_address,
        )

        shopify_order = OrderFields(**order_data)
        result = self.importer._import_one(shopify_order)

        self.assertTrue(result)
        mock_process_address.assert_called_once()

    def test_get_special_product_creates_new(self) -> None:
        product = self.importer._get_special_product("SPECIAL", "Special Product")

        self.assertTrue(product)
        self.assertEqual(product.default_code, "SPECIAL")
        self.assertEqual(product.name, "Special Product")
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.sale_ok)
        self.assertFalse(product.purchase_ok)

        product2 = self.importer._get_special_product("SPECIAL", "Different Name")
        self.assertEqual(product.id, product2.id)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_extreme_values(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True
        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            gid="gid://shopify/Order/999999999999999",
            name="#999999",
            total_price="999999.99",
            subtotal_price="999998.99",
            total_tax="1.00",
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.product_a.default_code,
                    quantity=9999,
                    unit_price="100.00",
                ),
            ],
        )

        imported_count = self._mock_fetch_page_and_import(OrderFields(**order_data))
        self.assertEqual(imported_count, 1)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "999999999999999")])
        self.assertTrue(order)
        self.assertGreater(order.amount_total, 999000)
        product_lines = order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines[0].product_uom_qty, 9999)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_unicode_characters(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True
        # noinspection SpellCheckingInspection
        order_data = create_shopify_order_response(
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.product_a.default_code,
                    name="Product with émojis 🚀 and Ñiño",
                    variant_title="Größe: 大きい & <small>",
                ),
            ],
            customer=create_shopify_customer_response(
                first_name="José",
                last_name="García-Pérez",
                email="test@例え.jp",
            ),
            note="Order note with 中文 and emoji 😊",
        )

        imported_count = self._mock_fetch_page_and_import(OrderFields(**order_data))
        self.assertEqual(imported_count, 1)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        self.assertTrue(order)
        product_lines = order.order_line.filtered(lambda l: not l.is_delivery and l.product_id.id == self.product_a.id)
        self.assertEqual(product_lines[0].name, "Product with émojis 🚀 and Ñiño")
        self.assertEqual(order.partner_id.id, self.customer_partner.id)  # We're mocking customer import
        self.assertIn("Order note with 中文 and emoji 😊", order.shopify_note)

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_null_optional_fields(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.product_a.default_code,
                    variant_title=None,
                    vendor=None,
                    requires_shipping=None,
                    gift_card=None,
                ),
            ],
        )

        imported_count = self._mock_fetch_page_and_import(OrderFields(**order_data))
        self.assertEqual(imported_count, 1)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        self.assertTrue(order)
        self.assertNotIn("Payment:", order.note or "")  # No payment info since we didn't provide any

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_malformed_data(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True
        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            total_price="100.00",
            subtotal_price="200.00",  # Subtotal > Total (inconsistent)
            total_tax="-10.00",  # Negative tax
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.product_a.default_code,
                    quantity=-1,  # Negative quantity
                    unit_price="0.00",  # Zero price
                ),
            ],
        )

        self._mock_fetch_page_with_error(order_data, ShopifyDataError)

    def test_import_order_api_timeout(self) -> None:
        self._mock_fetch_page_with_error(None, TimeoutError("API request timed out"))

    @patch.object(CustomerImporter, "import_customer")
    def test_import_order_with_duplicate_line_items(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            customer=create_shopify_customer_response(),
            line_items=[
                create_shopify_order_line_item_response(
                    gid="gid://shopify/LineItem/111",
                    sku=self.product_a.default_code,
                    quantity=2,
                    unit_price="50.00",
                ),
                create_shopify_order_line_item_response(
                    gid="gid://shopify/LineItem/222",
                    sku=self.product_a.default_code,
                    quantity=3,
                    unit_price="50.00",
                ),
            ],
        )

        imported_count = self._mock_fetch_page_and_import(OrderFields(**order_data))
        self.assertEqual(imported_count, 1)

        order = self.env["sale.order"].search([("shopify_order_id", "=", "123456789")])
        self.assertTrue(order)

        product_lines = order.order_line.filtered(lambda l: not l.is_delivery)
        self.assertEqual(len(product_lines), 2)
        self.assertEqual(sum(line.product_uom_qty for line in product_lines), 5)

    @patch.object(CustomerImporter, "import_customer")
    def test_shopify_note_populated_with_payment_and_note(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            note="Test order note",
            payment_gateway_names=["credit_card", "paypal"],
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
        )

        order = self._import_order_and_verify_success(OrderFields(**order_data))
        self.assertEqual(order.shopify_note, "Payment: credit_card, paypal\nTest order note")

    @patch.object(CustomerImporter, "import_customer")
    def test_ebay_order_includes_ebay_info_in_shopify_note(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True

        order_data = create_shopify_order_response(
            note="eBay order note",
            custom_attributes=[{"key": "Note Attributes", "value": "eBay Sales Record Number: 12345\neBay Order Id: 67890"}],
            customer=create_shopify_customer_response(),
            line_items=[create_shopify_order_line_item_response(sku=self.product_a.default_code)],
        )

        order = self._import_order_and_verify_success(OrderFields(**order_data))
        self.assertIn("eBay Sales Record: 12345", order.shopify_note)
        self.assertIn("eBay Order ID: 67890", order.shopify_note)
        self.assertIn("eBay order note", order.shopify_note)
        self.assertEqual(order.source_platform, "ebay")
