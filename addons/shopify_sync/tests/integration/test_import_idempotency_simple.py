from datetime import timezone
from typing import Any
from ..common_imports import tagged, datetime, timedelta, patch, MagicMock, INTEGRATION_TAGS
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ProductFactory, ShopifySyncFactory
from ..fixtures.shopify_responses import (
    create_shopify_order_response,
    create_shopify_customer_response,
    create_shopify_order_line_item_response,
)
from ...services.shopify.gql import OrderFields
from ...services.shopify.sync.importers.order_importer import OrderImporter
from ...services.shopify.helpers import last_import_config_key, format_datetime_for_shopify


@tagged(*INTEGRATION_TAGS)
class TestImportIdempotencySimple(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()
        self.create_shopify_credentials()
        self._setup_import_idempotency_test()

        self.env["ir.config_parameter"].search([("key", "like", "shopify.last_import.%")]).unlink()

    def _setup_import_idempotency_test(self) -> None:
        self.test_product = ProductFactory.create(
            self.env,
            default_code="80000002",
            list_price=100.0,
            standard_price=50.0,
        ).product_variant_id
        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_orders")

    def test_import_since_last_import_filters_correctly(self) -> None:
        importer = OrderImporter(self.env, self.sync_record)

        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        new_time = datetime.now(timezone.utc)

        old_order_data = create_shopify_order_response(
            gid="gid://shopify/Order/1101",
            name="#OLD-001",
            created_at=old_time.isoformat(),
            updated_at=old_time.isoformat(),
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/2101", email="old@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )

        new_order_data = create_shopify_order_response(
            gid="gid://shopify/Order/1102",
            name="#NEW-001",
            created_at=new_time.isoformat(),
            updated_at=new_time.isoformat(),
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/2102", email="new@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )

        middle_time = old_time + timedelta(hours=1)
        config_key = last_import_config_key("order")
        self.env["ir.config_parameter"].set_param(config_key, format_datetime_for_shopify(middle_time))

        def mock_fetch_page(_client: Any, query: str | None, cursor: str | None) -> MagicMock:
            mock_page = MagicMock()

            if query and 'updated_at:>"' in query:
                if cursor is None:
                    mock_page.nodes = [OrderFields(**new_order_data)]
                else:
                    mock_page.nodes = []
            else:
                if cursor is None:
                    mock_page.nodes = [OrderFields(**old_order_data), OrderFields(**new_order_data)]
                else:
                    mock_page.nodes = []

            mock_page.page_info = MagicMock()
            mock_page.page_info.has_next_page = False
            mock_page.page_info.end_cursor = None

            return mock_page

        with patch.object(importer, "_fetch_page", side_effect=mock_fetch_page):
            count = importer.import_orders_since_last_import()
            self.assertEqual(count, 1)

        orders = self.env["sale.order"].search([("shopify_order_id", "!=", False)])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].shopify_order_id, "1102")
        self.assertEqual(orders[0].name, "#NEW-001")

    def test_first_import_gets_all_data(self) -> None:
        importer = OrderImporter(self.env, self.sync_record)

        order_data = create_shopify_order_response(
            gid="gid://shopify/Order/1103",
            name="#FIRST-001",
            customer=create_shopify_customer_response(gid="gid://shopify/Customer/2103", email="first@test.com"),
            line_items=[
                create_shopify_order_line_item_response(
                    sku=self.test_product.default_code,
                    variant_id="987654321",
                )
            ],
        )

        config_key = last_import_config_key("order")
        self.assertFalse(self.env["ir.config_parameter"].get_param(config_key))

        def mock_fetch_page(_client: Any, _query: str | None, cursor: str | None) -> MagicMock:
            mock_page = MagicMock()

            if cursor is None:
                mock_page.nodes = [OrderFields(**order_data)]
            else:
                mock_page.nodes = []

            mock_page.page_info = MagicMock()
            mock_page.page_info.has_next_page = False
            mock_page.page_info.end_cursor = None

            return mock_page

        with patch.object(importer, "_fetch_page", side_effect=mock_fetch_page):
            count = importer.import_orders_since_last_import()
            self.assertEqual(count, 1)

        orders = self.env["sale.order"].search([("shopify_order_id", "=", "1103")])
        self.assertEqual(len(orders), 1)
