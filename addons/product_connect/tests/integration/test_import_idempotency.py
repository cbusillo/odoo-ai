from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ProductFactory, ShopifySyncFactory
from ..fixtures.shopify_responses import (
    create_shopify_order_response,
    create_shopify_customer_response,
    create_shopify_product_response,
    create_shopify_order_line_item_response,
    create_shopify_variant_response,
    create_shopify_address_response,
)
from ...services.shopify.gql import OrderFields, CustomerFields, ProductFields
from ...services.shopify.sync.importers.order_importer import OrderImporter
from ...services.shopify.sync.importers.customer_importer import CustomerImporter
from ...services.shopify.sync.importers.product_importer import ProductImporter


@tagged(*INTEGRATION_TAGS)
class TestImportIdempotencyUnit(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()
        self.create_shopify_credentials()
        self._setup_import_idempotency_test()

    def _setup_import_idempotency_test(self) -> None:
        self.test_product = ProductFactory.create(
            self.env,
            default_code="80000001",
            list_price=100.0,
            standard_price=50.0,
        ).product_variant_id
        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_orders")

    def test_order_import_creates_new_order(self) -> None:
        importer = OrderImporter(self.env, self.sync_record)

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/new_order_1",
            name="#NEW-001",
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/cust_1", email="customer1@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )
        order = OrderFields(**order_data)

        result = importer._import_one(order)

        self.assertTrue(result)

        orders = self.env["sale.order"].search([("shopify_order_id", "=", "new_order_1")])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].name, "#NEW-001")

    def test_order_import_existing_unchanged_returns_false(self) -> None:
        importer = OrderImporter(self.env, self.sync_record)

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/existing_order_1",
            name="#EXIST-001",
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/cust_2", email="customer2@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )
        order = OrderFields(**order_data)

        result1 = importer._import_one(order)
        self.assertTrue(result1)

        result2 = importer._import_one(order)

        self.assertFalse(result2)

        orders = self.env["sale.order"].search([("shopify_order_id", "=", "existing_order_1")])
        self.assertEqual(len(orders), 1)

    def test_order_import_with_updates_returns_true(self) -> None:
        importer = OrderImporter(self.env, self.sync_record)

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/update_order_1",
            name="#UPDATE-001",
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/cust_3", email="customer3@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )
        order = OrderFields(**order_data)

        result1 = importer._import_one(order)
        self.assertTrue(result1)

        updated_order_data = create_shopify_order_response(
            gid="gid://shopify/Order/update_order_1",
            name="#UPDATE-001",
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/cust_3", email="customer3@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                    quantity=2,
                )
            ],
        )
        updated_order = OrderFields(**updated_order_data)

        result2 = importer._import_one(updated_order)

        self.assertTrue(result2)

        orders = self.env["sale.order"].search([("shopify_order_id", "=", "update_order_1")])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_line[0].product_uom_qty, 2)

    def test_customer_import_creates_new_customer(self) -> None:
        importer = CustomerImporter(self.env, self.sync_record)

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/new_customer_1",
            email="newcustomer@test.com",
            first_name="New",
            last_name="Customer",
        )
        customer = CustomerFields(**customer_data)

        result = importer.import_customer(customer)

        self.assertTrue(result)

        customers = self.env["res.partner"].search([("shopify_customer_id", "=", "new_customer_1")])
        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0].email, "newcustomer@test.com")

    def test_customer_import_existing_unchanged_returns_false(self) -> None:
        importer = CustomerImporter(self.env, self.sync_record)

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/existing_customer_1",
            email="existing@test.com",
            first_name="Existing",
            last_name="Customer",
        )
        customer = CustomerFields(**customer_data)

        result1 = importer.import_customer(customer)
        self.assertTrue(result1)

        result2 = importer.import_customer(customer)

        self.assertFalse(result2)

        customers = self.env["res.partner"].search([("shopify_customer_id", "=", "existing_customer_1")])
        self.assertEqual(len(customers), 1)

    def test_customer_import_with_new_address_returns_true(self) -> None:
        importer = CustomerImporter(self.env, self.sync_record)

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/address_customer_1",
            email="address@test.com",
            first_name="Address",
            last_name="Customer",
            **{
                "defaultAddress": None,
                "addressesV2": {"nodes": []},
            },
        )
        customer = CustomerFields(**customer_data)

        result1 = importer.import_customer(customer)
        self.assertTrue(result1)

        customers = self.env["res.partner"].search([("shopify_customer_id", "=", "address_customer_1")])
        self.assertEqual(len(customers), 1)
        self.assertFalse(customers[0].street)

        address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/addr_1",
            address1="123 New Street",
            city="New City",
        )
        updated_customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/address_customer_1",
            email="address@test.com",
            first_name="Address",
            last_name="Customer",
            default_address=address,
            addresses=[address],
        )
        updated_customer = CustomerFields(**updated_customer_data)

        result2 = importer.import_customer(updated_customer)

        self.assertTrue(result2)

        customers = self.env["res.partner"].search([("shopify_customer_id", "=", "address_customer_1")])
        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0].street, "123 New Street")

    def test_product_import_creates_new_product(self) -> None:
        importer = ProductImporter(self.env, self.sync_record)

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/new_product_1",
            title="New Product",
            vendor="Test Manufacturer",
            product_type="Motors",
            variants=[
                create_shopify_variant_response(
                    gid="gid://shopify/ProductVariant/new_variant_1",
                    sku="NEW001",
                    price="149.99",
                )
            ],
        )
        product = ProductFields(**product_data)

        result = importer._import_one(product)

        self.assertTrue(result)

        products = self.env["product.product"].search([("shopify_product_id", "=", "new_product_1")])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "New Product")
        self.assertEqual(products[0].default_code, "NEW001")

    def test_product_import_existing_with_old_timestamp_returns_false(self) -> None:
        importer = ProductImporter(self.env, self.sync_record)

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/timestamp_product_1",
            title="Timestamp Product",
            vendor="Test Manufacturer",
            product_type="Motors",
            created_at="2023-01-01T00:00:00Z",
            updated_at="2023-01-01T00:00:00Z",
            variants=[
                create_shopify_variant_response(
                    gid="gid://shopify/ProductVariant/timestamp_variant_1",
                    sku="TIME001",
                    price="199.99",
                )
            ],
        )
        product = ProductFields(**product_data)

        result1 = importer._import_one(product)
        self.assertTrue(result1)

        result2 = importer._import_one(product)

        self.assertFalse(result2)

        products = self.env["product.product"].search([("shopify_product_id", "=", "timestamp_product_1")])
        self.assertEqual(len(products), 1)

    def test_product_import_uses_first_variant(self) -> None:
        importer = ProductImporter(self.env, self.sync_record)

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/multi_variant_product",
            title="Multi Variant Product",
            vendor="Test Manufacturer",
            product_type="Motors",
            variants=[
                create_shopify_variant_response(
                    gid="gid://shopify/ProductVariant/variant_1",
                    sku="MULTI001",
                ),
                create_shopify_variant_response(
                    gid="gid://shopify/ProductVariant/variant_2",
                    sku="MULTI002",
                    price="149.99",
                ),
            ],
        )
        product = ProductFields(**product_data)

        result = importer._import_one(product)

        self.assertTrue(result)

        variants = self.env["product.product"].search([("shopify_product_id", "=", "multi_variant_product")])
        self.assertEqual(len(variants), 1)

        self.assertEqual(variants[0].default_code, "MULTI001")
        self.assertEqual(variants[0].shopify_variant_id, "variant_1")
