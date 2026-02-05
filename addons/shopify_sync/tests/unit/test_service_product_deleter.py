from ..common_imports import tagged, MagicMock, patch, UNIT_TAGS

from ...services.shopify.sync.deleters.product_deleter import ProductDeleter
from ...services.shopify.helpers import ShopifyApiError
from ariadne_codegen.client_generators.dependencies.exceptions import GraphQLClientGraphQLMultiError, GraphQLClientGraphQLError
from httpx import HTTPError
from ..fixtures.base import UnitTestCase


class DummySync:
    def __init__(self) -> None:
        self.id = 1
        self.hard_throttle_count = 0
        self.total_count = 0
        self.updated_count = 0

    def ensure_not_canceled(self) -> None:
        return


@tagged(*UNIT_TAGS)
class TestProductDeleter(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()

        self.deleter = ProductDeleter(self.env, DummySync())
        self.deleter.service._client = self.mock_client

    def test_fetch_product_ids_page_success(self) -> None:
        expected = object()
        self.deleter.service.client.get_product_ids.return_value = expected
        result = self.deleter._fetch_product_ids_page(None, "c1")
        self.assertIs(result, expected)
        self.deleter.service.client.get_product_ids.assert_called_once_with(cursor="c1", limit=self.deleter.page_size)

    def test_fetch_product_ids_page_error(self) -> None:
        error = GraphQLClientGraphQLMultiError([GraphQLClientGraphQLError("boom")])
        self.deleter.service.client.get_product_ids.side_effect = error
        with self.assertRaises(ShopifyApiError):
            self.deleter._fetch_product_ids_page(None, None)

    def test_delete_one_success(self) -> None:
        node = MagicMock(id="gid")
        self.deleter._delete_one(node)
        self.deleter.service.client.delete_product.assert_called_once()

    def test_delete_one_error(self) -> None:
        node = MagicMock(id="gid")
        self.deleter.service.client.delete_product.side_effect = HTTPError("bad")
        with self.assertRaises(ShopifyApiError):
            self.deleter._delete_one(node)

    def test_delete_all_products_calls_collect_and_run(self) -> None:
        with (
            patch.object(ProductDeleter, ProductDeleter.collect_nodes.__name__, return_value=[MagicMock(id="gid")]) as collect,
            patch.object(ProductDeleter, ProductDeleter.run.__name__) as run,
        ):
            self.deleter.delete_all_products()
            collect.assert_called_once_with(self.deleter._fetch_product_ids_page)
            run.assert_called_once_with(collect.return_value)
