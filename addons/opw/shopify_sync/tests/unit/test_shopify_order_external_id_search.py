from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import SaleOrderFactory, SaleOrderLineFactory


@common.tagged(*common.UNIT_TAGS)
class TestShopifyOrderExternalIdAccessors(UnitTestCase):
    def test_sale_order_uses_bound_external_id_api(self) -> None:
        order = SaleOrderFactory.create(self.env, name="Shopify Match Order")

        order.external_reference.id = "1001"

        self.assertEqual(order.external_reference.id, "1001")
        self.assertEqual(self.env["sale.order"].search_by_bound_external_id("1001"), order)


@common.tagged(*common.UNIT_TAGS)
class TestShopifyOrderLineExternalIdAccessors(UnitTestCase):
    def test_sale_order_line_uses_bound_external_id_api(self) -> None:
        order_line = SaleOrderLineFactory.create(self.env, name="Shopify Match Line")

        order_line.external_reference.id = "1001"

        self.assertEqual(order_line.external_reference.id, "1001")
        self.assertEqual(self.env["sale.order.line"].search_by_bound_external_id("1001"), order_line)

    def test_sale_order_line_accepts_synthetic_shopify_keys(self) -> None:
        order_line = SaleOrderLineFactory.create(self.env, name="Synthetic Shopify Line")

        order_line.external_reference.id = "tax:123456789:Sales Tax"

        self.assertEqual(order_line.external_reference.id, "tax:123456789:Sales Tax")
