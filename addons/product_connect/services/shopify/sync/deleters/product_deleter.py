import logging

import httpx
from ariadne_codegen.client_generators.dependencies.exceptions import GraphQLClientGraphQLMultiError
from odoo.api import Environment

from ...gql import ProductDeleteInput, GetProductIdsProductsNodes
from ...helpers import ShopifyApiError
from ..base import ShopifyBaseDeleter, ShopifyPage

_logger = logging.getLogger(__name__)


class ProductDeleter(ShopifyBaseDeleter[GetProductIdsProductsNodes]):
    api_errors = (GraphQLClientGraphQLMultiError, httpx.HTTPError)

    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        super().__init__(env, sync_record)

    def _fetch_product_ids_page(self, _: str | None, cursor: str | None) -> ShopifyPage[GetProductIdsProductsNodes]:
        try:
            return self.service.client.get_product_ids(cursor=cursor, limit=self.page_size)
        except self.api_errors as error:
            raise ShopifyApiError("Failed to fetch product IDs from Shopify") from error

    def delete_all_products(self) -> None:
        nodes = self.collect_nodes(self._fetch_product_ids_page)
        self.run(nodes)

    def _delete_one(self, node: GetProductIdsProductsNodes) -> None:
        delete_input = ProductDeleteInput(id=node.id)
        try:
            self.service.client.delete_product(delete_input)
        except self.api_errors as error:
            raise ShopifyApiError("Error deleting product", shopify_input=delete_input) from error
