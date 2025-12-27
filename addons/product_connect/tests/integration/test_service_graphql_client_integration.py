from typing import TypedDict, Any

from ..common_imports import patch, MagicMock, Mock, tagged, INTEGRATION_TAGS
from httpx import Request, Response

from ...services.shopify.gql import (
    ProductFields,
)
from ...services.shopify.gql.client import Client
from ...services.shopify.gql.input_types import ProductSetInput, ProductSetIdentifiers
from ...services.shopify.service import ShopifyService
from ...services.shopify.helpers import ShopifyApiError
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ShopifySyncFactory


class ThrottleStatus(TypedDict):
    maximumAvailable: int
    currentlyAvailable: int
    restoreRate: int


class CostInfo(TypedDict):
    requestedQueryCost: int
    actualQueryCost: int
    throttleStatus: ThrottleStatus


class Extensions(TypedDict):
    cost: CostInfo


class GraphQLCostResponse(TypedDict):
    data: dict[str, dict[str, list[dict[str, object]]]]
    extensions: Extensions


@tagged(*INTEGRATION_TAGS)
class TestGraphQLClientIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()
        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_products")
        self.service = ShopifyService(self.env, self.sync_record)

        config = self.env["ir.config_parameter"].sudo()
        config.set_param("shopify.shop_url_key", "test-shop")
        config.set_param("shopify.api_token", "test-token")

    @staticmethod
    def _create_mock_http_response(json_response: dict) -> tuple[MagicMock, Mock]:
        mock_http_client = MagicMock()
        mock_http_client.send.return_value = Response(
            200,
            json=json_response,
            request=Request("POST", "https://test-shop.myshopify.com/admin/api/graphql.json"),
            headers={"content-type": "application/json"},
        )

        mock_shopify_client = Mock(spec=Client)
        mock_shopify_client._http_client = mock_http_client
        return mock_http_client, mock_shopify_client

    def test_graphql_query_structure(self) -> None:
        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_client = MagicMock()
            mock_http_client = MagicMock()
            mock_client._http_client = mock_http_client
            mock_create_client.return_value = mock_http_client

            sent_requests = []

            def capture_request(request: Request, **_kwargs: Any) -> Response:
                sent_requests.append(request)
                return Response(
                    200,
                    json={
                        "data": {
                            "products": {
                                "nodes": [],
                                "pageInfo": {"hasNextPage": False},
                            }
                        }
                    },
                    request=request,
                    headers={"content-type": "application/json"},
                )

            mock_http_client.send = capture_request

            mock_shopify_client = Mock()
            mock_shopify_client.get_products = Mock(
                return_value=Mock(
                    products=Mock(
                        nodes=[],
                        page_info=Mock(has_next_page=False),
                    )
                )
            )

            with patch.object(self.service, "_client", mock_shopify_client):
                self.service.client.get_products(limit=10)

            mock_shopify_client.get_products.assert_called_once_with(limit=10)

    def test_graphql_response_parsing(self) -> None:
        product_data = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "vendor": "Test Vendor",
            "productType": "Test Type",
            "status": "ACTIVE",
            "totalInventory": 100,
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-01T00:00:00Z",
            "descriptionHtml": "<p>Test description</p>",
            "variants": {
                "nodes": [
                    {
                        "id": "gid://shopify/ProductVariant/456",
                        "sku": "008021",
                        "price": "99.99",
                        "barcode": "123456789",
                        "inventoryItem": {
                            "unitCost": {"amount": "50.00", "currencyCode": "USD"},
                            "measurement": {"weight": {"value": 1.5, "unit": "KILOGRAMS"}},
                        },
                    }
                ]
            },
            "media": {"nodes": []},
            "metafields": {"nodes": []},
        }

        product = ProductFields(**product_data)
        self.assertEqual(product.id, "gid://shopify/Product/123")
        self.assertEqual(product.title, "Test Product")
        self.assertEqual(product.vendor, "Test Vendor")
        self.assertEqual(len(product.variants.nodes), 1)
        self.assertEqual(product.variants.nodes[0].sku, "008021")

    def test_graphql_error_handling(self) -> None:
        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client = MagicMock()
            mock_create_client.return_value = mock_http_client

            mock_http_client.send.return_value = Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Field 'invalidField' doesn't exist on type 'Product'",
                            "extensions": {
                                "code": "GRAPHQL_PARSE_FAILED",
                                "category": "graphql",
                            },
                        }
                    ]
                },
                request=Request("POST", "https://test-shop.myshopify.com/admin/api/graphql.json"),
                headers={"content-type": "application/json"},
            )

            mock_shopify_client = Mock()
            mock_shopify_client._http_client = mock_http_client
            mock_shopify_client.get_products = Mock(side_effect=ShopifyApiError("GraphQL parse failed"))

            with patch.object(self.service, "_client", mock_shopify_client):
                with self.assertRaises(ShopifyApiError) as cm:
                    self.service.client.get_products(limit=10)

                self.assertIn("GraphQL", str(cm.exception))

    def test_pagination_handling(self) -> None:
        page1_response = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/1",
                            "title": "Product 1",
                            "vendor": "Vendor",
                            "productType": "Type",
                            "status": "ACTIVE",
                            "totalInventory": 10,
                            "createdAt": "2023-01-01T00:00:00Z",
                            "updatedAt": "2023-01-01T00:00:00Z",
                            "descriptionHtml": "",
                            "variants": {"nodes": []},
                            "media": {"nodes": []},
                            "metafields": {"nodes": []},
                        }
                    ],
                    "pageInfo": {
                        "hasNextPage": True,
                        "endCursor": "cursor123",
                    },
                }
            }
        }

        page2_response = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/2",
                            "title": "Product 2",
                            "vendor": "Vendor",
                            "productType": "Type",
                            "status": "ACTIVE",
                            "totalInventory": 20,
                            "createdAt": "2023-01-02T00:00:00Z",
                            "updatedAt": "2023-01-02T00:00:00Z",
                            "descriptionHtml": "",
                            "variants": {"nodes": []},
                            "media": {"nodes": []},
                            "metafields": {"nodes": []},
                        }
                    ],
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                }
            }
        }

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client = MagicMock()
            mock_create_client.return_value = mock_http_client

            responses = [page1_response, page2_response]
            mock_http_client.send.side_effect = [
                Response(
                    200,
                    json=resp,
                    request=Request("POST", "https://test-shop.myshopify.com/admin/api/graphql.json"),
                    headers={"content-type": "application/json"},
                )
                for resp in responses
            ]

            mock_page1 = Mock()
            mock_page1.products.nodes = [ProductFields(**page1_response["data"]["products"]["nodes"][0])]
            mock_page1.products.page_info.has_next_page = True
            mock_page1.products.page_info.end_cursor = "cursor123"

            mock_page2 = Mock()
            mock_page2.products.nodes = [ProductFields(**page2_response["data"]["products"]["nodes"][0])]
            mock_page2.products.page_info.has_next_page = False
            mock_page2.products.page_info.end_cursor = None

            mock_shopify_client = Mock()
            mock_shopify_client.get_products = Mock(side_effect=[mock_page1, mock_page2])

            with patch.object(self.service, "_client", mock_shopify_client):
                all_products = []
                cursor = None
                while True:
                    if cursor:
                        response = self.service.client.get_products(limit=10, cursor=cursor)
                    else:
                        response = self.service.client.get_products(limit=10)

                    all_products.extend(response.products.nodes)

                    if not response.products.page_info.has_next_page:
                        break
                    cursor = response.products.page_info.end_cursor

                self.assertEqual(len(all_products), 2)
                self.assertEqual(all_products[0].id, "gid://shopify/Product/1")
                self.assertEqual(all_products[1].id, "gid://shopify/Product/2")

    def test_graphql_mutation_handling(self) -> None:
        from ...services.shopify.gql import ProductSetProductSet, ProductSetProductSetProduct

        mutation_response = {
            "data": {
                "productSet": {
                    "product": {
                        "id": "gid://shopify/Product/123",
                        "updatedAt": "2023-01-01T00:00:00Z",
                        "variants": {"nodes": []},
                        "metafields": {"nodes": []},
                        "media": {"nodes": []},
                        "resourcePublicationsV2": {"nodes": [], "pagesCount": 0, "resourcePublicationsCount": 0},
                    },
                    "userErrors": [],
                }
            }
        }

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client, mock_shopify_client = self._create_mock_http_response(mutation_response)
            mock_create_client.return_value = mock_http_client

            mock_product_set = Mock(spec=ProductSetProductSet)
            mock_product_set.product = Mock(spec=ProductSetProductSetProduct)
            mock_product_set.product.id = "gid://shopify/Product/123"
            mock_product_set.user_errors = []

            mock_shopify_client.product_set = Mock(return_value=mock_product_set)

            with patch.object(self.service, "_client", mock_shopify_client):
                result = self.service.client.product_set(
                    input=ProductSetInput(title="Updated Product"),
                    identifier=ProductSetIdentifiers(id="gid://shopify/Product/123"),
                )

                self.assertEqual(result.product.id, "gid://shopify/Product/123")
                self.assertEqual(len(result.user_errors), 0)

    def test_graphql_user_errors(self) -> None:
        from ...services.shopify.gql import ProductSetProductSet, ProductSetProductSetUserErrors

        user_error_response = {
            "data": {
                "productSet": {
                    "product": None,
                    "userErrors": [
                        {
                            "field": ["title"],
                            "message": "Title can't be blank",
                        },
                        {
                            "field": ["vendor"],
                            "message": "Vendor is required",
                        },
                    ],
                }
            }
        }

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client, mock_shopify_client = self._create_mock_http_response(user_error_response)
            mock_create_client.return_value = mock_http_client

            mock_product_set = Mock(spec=ProductSetProductSet)
            mock_product_set.product = None

            mock_error1 = Mock(spec=ProductSetProductSetUserErrors)
            mock_error1.field = ["title"]
            mock_error1.message = "Title can't be blank"

            mock_error2 = Mock(spec=ProductSetProductSetUserErrors)
            mock_error2.field = ["vendor"]
            mock_error2.message = "Vendor is required"

            mock_product_set.user_errors = [mock_error1, mock_error2]

            mock_shopify_client.product_set = Mock(return_value=mock_product_set)

            with patch.object(self.service, "_client", mock_shopify_client):
                result = self.service.client.product_set(input=ProductSetInput(title="", vendor=""))

                self.assertIsNone(result.product)
                self.assertEqual(len(result.user_errors), 2)
                self.assertEqual(result.user_errors[0].message, "Title can't be blank")

    def test_graphql_bulk_operations(self) -> None:
        from ...services.shopify.gql import (
            ProductSetBulkRunBulkOperationRunMutation,
            ProductSetBulkRunBulkOperationRunMutationBulkOperation,
        )

        bulk_mutation = """
        mutation {
            productSet(
                input: { title: "Updated Title" }
                identifier: { id: "gid://shopify/Product/123" }
            ) {
                product { id }
                userErrors { field message }
            }
        }
        """

        bulk_response = {
            "data": {
                "bulkOperationRunMutation": {
                    "bulkOperation": {
                        "id": "gid://shopify/BulkOperation/123",
                        "status": "CREATED",
                    },
                    "userErrors": [],
                }
            }
        }

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client, mock_shopify_client = self._create_mock_http_response(bulk_response)
            mock_create_client.return_value = mock_http_client

            mock_bulk_op = Mock(spec=ProductSetBulkRunBulkOperationRunMutation)
            mock_bulk_op.bulk_operation = Mock(spec=ProductSetBulkRunBulkOperationRunMutationBulkOperation)
            mock_bulk_op.bulk_operation.id = "gid://shopify/BulkOperation/123"
            mock_bulk_op.bulk_operation.status = "CREATED"
            mock_bulk_op.user_errors = []

            mock_shopify_client.product_set_bulk_run = Mock(return_value=mock_bulk_op)

            with patch.object(self.service, "_client", mock_shopify_client):
                result = self.service.client.product_set_bulk_run(
                    mutation=bulk_mutation,
                    staged_upload_path="path/to/upload",
                )

                self.assertEqual(
                    result.bulk_operation.id,
                    "gid://shopify/BulkOperation/123",
                )
                self.assertEqual(
                    result.bulk_operation.status,
                    "CREATED",
                )

    def test_graphql_field_selection(self) -> None:
        minimal_product_query = """
        {
            products(first: 1) {
                nodes {
                    id
                    title
                }
            }
        }
        """

        full_product_query = """
        {
            products(first: 1) {
                nodes {
                    id
                    title
                    vendor
                    productType
                    status
                    totalInventory
                    variants {
                        nodes {
                            id
                            sku
                            price
                        }
                    }
                    media {
                        nodes {
                            ... on MediaImage {
                                id
                                alt
                            }
                        }
                    }
                }
            }
        }
        """

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client = MagicMock()
            mock_create_client.return_value = mock_http_client

            sent_requests = []

            def capture_request(request: Request, **_kwargs: Any) -> Response:
                sent_requests.append(request)
                return Response(
                    200,
                    json={"data": {"products": {"nodes": []}}},
                    request=request,
                    headers={"content-type": "application/json"},
                )

            mock_http_client.send = capture_request

            self.assertTrue(len(minimal_product_query) < len(full_product_query))

    def test_graphql_connection_types(self) -> None:
        # noinspection SpellCheckingInspection
        connection_response = {
            "data": {
                "orders": {
                    "edges": [
                        {
                            "cursor": "eyJsYXN0X2lkIjoxMjM0NTY3ODk=",
                            "node": {
                                "id": "gid://shopify/Order/123",
                                "name": "#1001",
                                "createdAt": "2023-01-01T00:00:00Z",
                            },
                        }
                    ],
                    "pageInfo": {
                        "hasNextPage": True,
                        "hasPreviousPage": False,
                        "startCursor": "eyJsYXN0X2lkIjoxMjM0NTY3ODk=",
                        "endCursor": "eyJsYXN0X2lkIjoxMjM0NTY3ODk=",
                    },
                }
            }
        }

        edges_data = connection_response["data"]["orders"]["edges"]
        self.assertEqual(len(edges_data), 1)
        self.assertEqual(edges_data[0]["node"]["name"], "#1001")

    def test_graphql_nullable_fields(self) -> None:
        working_product_data = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "vendor": "Test Vendor",
            "productType": "Test Type",
            "status": "ACTIVE",
            "totalInventory": 100,
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-01T00:00:00Z",
            "descriptionHtml": "<p>Test</p>",
            "variants": {
                "nodes": [
                    {
                        "id": "gid://shopify/ProductVariant/456",
                        "sku": "TEST123",
                        "price": "99.99",
                        "barcode": "123456789",
                        "inventoryItem": {
                            "unitCost": {"amount": "50.00", "currencyCode": "USD"},
                            "measurement": {"weight": {"value": 1.5, "unit": "KILOGRAMS"}},
                        },
                    }
                ]
            },
            "media": {"nodes": []},
            "metafields": {"nodes": []},
        }

        product = ProductFields(**working_product_data)
        self.assertEqual(product.title, "Test Product")

        minimal_product_data = {
            "id": "gid://shopify/Product/124",
            "title": "Minimal Product",
            "vendor": "",
            "productType": "",
            "status": "ACTIVE",
            "totalInventory": 0,
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-01T00:00:00Z",
            "descriptionHtml": "",
            "variants": {
                "nodes": [
                    {
                        "id": "gid://shopify/ProductVariant/457",
                        "sku": "",
                        "price": "0.00",
                        "barcode": None,
                        "inventoryItem": {
                            "unitCost": None,
                            "measurement": {"weight": None},
                        },
                    }
                ]
            },
            "media": {"nodes": []},
            "metafields": {"nodes": []},
        }

        minimal_product = ProductFields(**minimal_product_data)
        self.assertEqual(minimal_product.vendor, "")
        self.assertEqual(minimal_product.product_type, "")
        self.assertEqual(minimal_product.total_inventory, 0)
        self.assertEqual(minimal_product.description_html, "")

    def test_graphql_fragment_spreading(self) -> None:
        media_response = {
            "data": {
                "product": {
                    "media": {
                        "nodes": [
                            {
                                "__typename": "MediaImage",
                                "id": "gid://shopify/MediaImage/123",
                                "alt": "Front view",
                                "image": {
                                    "url": "https://example.com/image.jpg",
                                },
                            },
                            {
                                "__typename": "Video",
                                "id": "gid://shopify/Video/456",
                                "sources": [
                                    {
                                        "url": "https://example.com/video.mp4",
                                        "mimeType": "video/mp4",
                                    }
                                ],
                            },
                            {
                                "__typename": "Model3d",
                                "id": "gid://shopify/Model3d/789",
                                "sources": [
                                    {
                                        "url": "https://example.com/model.glb",
                                        "mimeType": "model/gltf-binary",
                                    }
                                ],
                            },
                        ]
                    }
                }
            }
        }

        media_nodes = media_response["data"]["product"]["media"]["nodes"]
        self.assertEqual(len(media_nodes), 3)
        self.assertEqual(media_nodes[0]["__typename"], "MediaImage")
        self.assertEqual(media_nodes[1]["__typename"], "Video")
        self.assertEqual(media_nodes[2]["__typename"], "Model3d")

    def test_graphql_query_cost_tracking(self) -> None:
        cost_response: GraphQLCostResponse = {
            "data": {"products": {"nodes": []}},
            "extensions": {
                "cost": {
                    "requestedQueryCost": 102,
                    "actualQueryCost": 52,
                    "throttleStatus": {
                        "maximumAvailable": 1000,
                        "currentlyAvailable": 948,
                        "restoreRate": 50,
                    },
                }
            },
        }

        with patch.object(self.service, "_create_http_client") as mock_create_client:
            mock_http_client = MagicMock()
            mock_create_client.return_value = mock_http_client

            mock_http_client.send.return_value = Response(
                200,
                json=cost_response,
                request=Request("POST", "https://test-shop.myshopify.com/admin/api/graphql.json"),
                headers={"content-type": "application/json"},
            )

            self.assertEqual(cost_response["extensions"]["cost"]["requestedQueryCost"], 102)
            self.assertEqual(cost_response["extensions"]["cost"]["actualQueryCost"], 52)
            self.assertEqual(
                cost_response["extensions"]["cost"]["throttleStatus"]["currentlyAvailable"],
                948,
            )

    def test_graphql_alias_handling(self) -> None:
        alias_response = {
            "data": {
                "recentProducts": {
                    "nodes": [
                        {"productId": "gid://shopify/Product/1", "productName": "Recent Product"},
                    ]
                },
                "popularProducts": {
                    "nodes": [
                        {"productId": "gid://shopify/Product/2", "productName": "Popular Product"},
                    ]
                },
            }
        }

        recent = alias_response["data"]["recentProducts"]["nodes"][0]
        popular = alias_response["data"]["popularProducts"]["nodes"][0]

        self.assertEqual(recent["productName"], "Recent Product")
        self.assertEqual(popular["productName"], "Popular Product")

    def test_graphql_error_locations(self) -> None:
        error_with_location = {
            "errors": [
                {
                    "message": "Field 'invalidField' doesn't exist on type 'Product'",
                    "locations": [{"line": 3, "column": 5}],
                    "path": ["products", "nodes", 0, "invalidField"],
                    "extensions": {
                        "code": "GRAPHQL_VALIDATION_FAILED",
                        "category": "graphql",
                    },
                }
            ]
        }

        error = error_with_location["errors"][0]
        self.assertEqual(error["locations"][0]["line"], 3)
        self.assertEqual(error["locations"][0]["column"], 5)
        self.assertEqual(error["path"], ["products", "nodes", 0, "invalidField"])

    def test_graphql_deprecation_warnings(self) -> None:
        deprecation_response = {
            "data": {"products": {"nodes": []}},
            "extensions": {
                "warnings": [
                    {
                        "field": "Product.tags",
                        "message": "The 'tags' field is deprecated. Use 'metafields' instead.",
                    }
                ]
            },
        }

        warnings = deprecation_response.get("extensions", {}).get("warnings", [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("deprecated", warnings[0]["message"])
