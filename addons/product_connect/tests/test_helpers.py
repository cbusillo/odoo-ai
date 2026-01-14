import contextlib
import random
import secrets
import string
import time
from datetime import datetime
from typing import Any, Generator, Optional, Protocol
from unittest.mock import MagicMock, patch

from odoo.models import BaseModel

from .base_types import TEST_SHOPIFY_ID_MAX, TEST_SHOPIFY_ID_MIN


def generate_unique_sku() -> str:
    return str(random.randint(10000000, 99999999))


def generate_unique_name(base_name: str) -> str:
    return f"{base_name} {datetime.now().timestamp()}"


def generate_shopify_id() -> str:
    return str(random.randint(TEST_SHOPIFY_ID_MIN, TEST_SHOPIFY_ID_MAX))


def generate_motor_serial() -> str:
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=7))
    return f"{letters}{numbers}"


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def assert_shopify_fields(record: object, expected: dict[str, object]) -> None:
    for field, value in expected.items():
        actual = getattr(record, field)
        assert actual == value, f"Field {field}: expected {value!r}, got {actual!r}"


class EnvironmentWithContext(Protocol):
    def with_context(self, **kwargs: object) -> "EnvironmentWithContext":
        ...


def with_test_context(env: EnvironmentWithContext) -> EnvironmentWithContext:
    from .base_types import DEFAULT_TEST_CONTEXT

    return env.with_context(**DEFAULT_TEST_CONTEXT)


@contextlib.contextmanager
def mock_shopify_service(
    return_value: Any = None,
    side_effect: Any = None,
) -> Generator[MagicMock, None, None]:
    with patch("product_connect.services.shopify.ShopifyService") as mock_service:
        if return_value is not None:
            mock_service.return_value = return_value
        if side_effect is not None:
            mock_service.side_effect = side_effect
        yield mock_service


@contextlib.contextmanager
def mock_graphql_client(
    execute_return: Optional[dict] = None,
    execute_side_effect: Any = None,
) -> Generator[MagicMock, None, None]:
    with patch("product_connect.services.shopify.gql.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance

        if execute_return is not None:
            mock_instance.execute.return_value = execute_return
        if execute_side_effect is not None:
            mock_instance.execute.side_effect = execute_side_effect

        yield mock_instance


@contextlib.contextmanager
def mock_datetime_now(fixed_datetime: datetime) -> Generator[None, None, None]:
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_datetime
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        yield


def assert_fields_equal(
    record: object,
    expected: dict[str, Any],
    message_prefix: str = "",
) -> None:
    errors = []
    for field, expected_value in expected.items():
        actual_value = getattr(record, field, None)
        if actual_value != expected_value:
            error = f"Field '{field}': expected {expected_value!r}, got {actual_value!r}"
            if message_prefix:
                error = f"{message_prefix} - {error}"
            errors.append(error)

    if errors:
        raise AssertionError("\n".join(errors))


def assert_record_count(
    model: BaseModel,
    domain: list,
    expected_count: int,
    message: Optional[str] = None,
) -> None:
    actual_count = model.search_count(domain)
    if actual_count != expected_count:
        msg = message or f"Expected {expected_count} records, found {actual_count}"
        msg += f"\nDomain: {domain}"
        raise AssertionError(msg)


def assert_in_log(
    log_records: list,
    expected_message: str,
    level: Optional[str] = None,
) -> None:
    for record in log_records:
        if expected_message in record.message:
            if level is None or record.levelname == level:
                return

    msg = f"Expected log message not found: {expected_message!r}"
    if level:
        msg += f" at level {level}"
    raise AssertionError(msg)


@contextlib.contextmanager
def measure_performance(
    operation_name: str,
    max_duration: Optional[float] = None,
) -> Generator[dict[str, Any], None, None]:
    metrics = {
        "operation": operation_name,
        "start_time": time.perf_counter(),
        "end_time": None,
        "duration": None,
    }

    try:
        yield metrics
    finally:
        metrics["end_time"] = time.perf_counter()
        metrics["duration"] = metrics["end_time"] - metrics["start_time"]

        if max_duration and metrics["duration"] > max_duration:
            raise AssertionError(
                f"Operation '{operation_name}' took {metrics['duration']:.3f}s, exceeding maximum of {max_duration:.3f}s"
            )


class TestDataBuilder:
    @staticmethod
    def shopify_response(
        data: Optional[dict] = None,
        errors: Optional[list] = None,
        extensions: Optional[dict] = None,
    ) -> dict[str, Any]:
        response = {}
        if data is not None:
            response["data"] = data
        if errors is not None:
            response["errors"] = errors
        if extensions is not None:
            response["extensions"] = extensions
        return response

    @staticmethod
    def shopify_product(
        product_id: Optional[str] = None,
        title: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        product = {
            "id": product_id or generate_shopify_id(),
            "title": title or generate_unique_name("Test Product"),
            "handle": kwargs.get("handle", "test-product"),
            "vendor": kwargs.get("vendor", "Test Vendor"),
            "productType": kwargs.get("productType", "Test Type"),
            "tags": kwargs.get("tags", []),
            "status": kwargs.get("status", "ACTIVE"),
        }
        product.update(kwargs)
        return product
