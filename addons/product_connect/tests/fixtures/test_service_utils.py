from typing import Any, Callable

from ..common_imports import MagicMock


def create_mock_fetch_page_function(
    _entity_type: str,
    data_list: list[dict[str, Any]],
    field_class: type,
    _has_page_info: bool = True,
) -> Callable:
    def mock_fetch_page(_client: Any, _query: str | None, cursor: str | None) -> MagicMock:
        mock_page = MagicMock()

        if cursor is None and data_list:
            mock_page.nodes = [field_class(**data) for data in data_list]
        else:
            mock_page.nodes = []

        mock_page.page_info = MagicMock()
        mock_page.page_info.has_next_page = False
        mock_page.page_info.end_cursor = None

        return mock_page

    return mock_fetch_page


def create_mock_graphql_response(
    entity_type: str,
    nodes: list[Any],
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> MagicMock:
    mock_response = MagicMock()

    if entity_type in ["orders", "customers"]:
        entity_mock = MagicMock()
        entity_mock.nodes = nodes
        entity_mock.page_info.has_next_page = has_next_page
        entity_mock.page_info.end_cursor = end_cursor
        setattr(mock_response, entity_type, entity_mock)
    else:
        mock_response.nodes = nodes
        mock_response.page_info.has_next_page = has_next_page
        mock_response.page_info.end_cursor = end_cursor

    return mock_response


def create_test_product_data(
    product_id: str = "123456",
    title: str = "Test Product",
    handle: str = "test-product",
    vendor: str = "Test Vendor",
    product_type: str = "Test Type",
) -> dict[str, Any]:
    return {
        "title": title,
        "handle": handle,
        "vendor": vendor,
        "product_type": product_type,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "published_at": "2024-01-01T00:00:00Z",
        "template_suffix": None,
        "status": "ACTIVE",
        "published_scope": "GLOBAL",
        "tags": [],
        "admin_graphql_api_id": f"gid://shopify/Product/{product_id}",
        "variants": MagicMock(nodes=[]),
        "images": MagicMock(nodes=[]),
        "options": [],
    }


def create_test_order_data(
    order_id: str = "123456",
    name: str = "#1001",
    email: str = "test@example.com",
    total_price: str = "100.00",
) -> dict[str, Any]:
    return {
        "admin_graphql_api_id": f"gid://shopify/Order/{order_id}",
        "name": name,
        "email": email,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "processed_at": "2024-01-01T00:00:00Z",
        "closed_at": None,
        "cancelled_at": None,
        "currency": "USD",
        "total_price": MagicMock(amount=total_price, currency_code="USD"),
        "subtotal_price": MagicMock(amount=total_price, currency_code="USD"),
        "total_tax": MagicMock(amount="0.00", currency_code="USD"),
        "total_shipping_price": MagicMock(amount="0.00", currency_code="USD"),
        "total_discounts": MagicMock(amount="0.00", currency_code="USD"),
        "financial_status": "PAID",
        "fulfillment_status": "UNFULFILLED",
        "line_items": MagicMock(nodes=[]),
        "shipping_lines": MagicMock(nodes=[]),
        "shipping_address": None,
        "billing_address": None,
        "customer": None,
        "note": None,
        "tags": [],
    }


def create_mock_simple_response(nodes: list[Any], has_next_page: bool = False, end_cursor: str | None = None) -> MagicMock:
    mock_response = MagicMock()
    mock_response.nodes = nodes

    page_info = MagicMock()
    page_info.has_next_page = has_next_page
    page_info.end_cursor = end_cursor
    mock_response.page_info = page_info

    return mock_response


def create_test_customer_data(
    customer_id: str = "123456",
    email: str = "test@example.com",
    first_name: str = "Test",
    last_name: str = "Customer",
) -> dict[str, Any]:
    return {
        "admin_graphql_api_id": f"gid://shopify/Customer/{customer_id}",
        "email": email,
        "email_marketing_consent": MagicMock(state="NOT_SUBSCRIBED"),
        "first_name": first_name,
        "last_name": last_name,
        "phone": None,
        "sms_marketing_consent": None,
        "tags": [],
        "tax_exempt": False,
        "tax_exemptions": [],
        "total_spent": MagicMock(amount="0.00", currency_code="USD"),
        "verified_email": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "note": None,
        "addresses": MagicMock(nodes=[]),
        "default_address": None,
    }
