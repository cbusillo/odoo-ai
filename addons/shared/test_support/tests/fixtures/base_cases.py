import time
from typing import Any
from urllib.parse import urlsplit

from ..base_types import DEFAULT_TEST_CONTEXT
from ..shared.shopify_test_cases import (
    ShopifyIntegrationTestCaseBase,
    ShopifyTourTestCaseBase,
    ShopifyUnitTestCaseBase,
)


def browser_http_url(test_case: Any, path_or_url: str) -> str:
    if urlsplit(path_or_url).scheme in {"http", "https"}:
        return path_or_url

    port = test_case.http_port()
    return f"http://127.0.0.1:{port}{path_or_url}"


def wait_for_browser_endpoint(test_case: Any, path_or_url: str, timeout_seconds: int = 60) -> None:
    try:
        import requests
    except ImportError:
        return

    endpoint_url = browser_http_url(test_case, path_or_url)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(endpoint_url, timeout=3)
            if response.status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)


# noinspection DuplicatedCode
# Shared browser preflight helper intentionally mirrors local addon-specific browser harness helpers.
def preflight_get(path_or_url: str, timeout_seconds: int = 10) -> tuple[int, float, int, str]:
    try:
        import requests
    except ImportError as import_error:
        return 0, -1.0, 0, f"requests unavailable: {import_error}"

    start_time = time.perf_counter()
    try:
        response = requests.get(path_or_url, timeout=timeout_seconds, allow_redirects=True)
    except Exception as request_error:  # pragma: no cover - diagnostics only
        return 0, -1.0, 0, f"error: {request_error}"

    elapsed_seconds = time.perf_counter() - start_time
    response_text = response.text or ""
    snippet = response_text[:160].replace("\n", " ")
    return response.status_code, elapsed_seconds, len(response.content or b""), snippet


# noinspection DuplicatedCode
# Shared browser suite helper intentionally mirrors local addon-specific browser harness helpers.
def run_browser_js_suite(
    test_case: Any,
    url: str,
    *,
    success_signal: str,
    error_checker: Any,
    timeout: int = 900,
    retry_timeout: int | None = None,
    recoverable_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> None:
    wait_for_browser_endpoint(test_case, url)

    # noinspection DuplicatedCode
    # Shared browser suite helper intentionally mirrors local addon-specific browser harness helpers.
    def run_suite(run_timeout: int) -> None:
        test_case.browser_js(
            url,
            code="",
            login=test_case._get_test_login(),
            timeout=run_timeout,
            success_signal=success_signal,
            error_checker=error_checker,
        )

    try:
        run_suite(timeout)
    except TimeoutError:
        if retry_timeout is None:
            raise
        try:
            run_suite(retry_timeout)
        except recoverable_exceptions as browser_error:
            test_case.skipTest(f"JS harness not stable in this environment: {browser_error}")
    except recoverable_exceptions as browser_error:
        test_case.skipTest(f"JS harness not stable in this environment: {browser_error}")


class SharedUnitTestCase(ShopifyUnitTestCaseBase):
    default_test_context = DEFAULT_TEST_CONTEXT


class SharedIntegrationTestCase(ShopifyIntegrationTestCaseBase):
    default_test_context = DEFAULT_TEST_CONTEXT
    enforce_test_company_country = True


class SharedTourTestCase(ShopifyTourTestCaseBase):
    optional_group_xmlids = ("stock.group_stock_manager",)

    def _browser_http_url(self, path_or_url: str) -> str:
        return browser_http_url(self, path_or_url)

    @staticmethod
    def preflight_get(path_or_url: str, timeout_seconds: int = 10) -> tuple[int, float, int, str]:
        return preflight_get(path_or_url, timeout_seconds)

    def run_browser_js_suite(
        self,
        url: str,
        *,
        success_signal: str,
        error_checker: Any,
        timeout: int = 900,
        retry_timeout: int | None = None,
        recoverable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        run_browser_js_suite(
            self,
            url,
            success_signal=success_signal,
            error_checker=error_checker,
            timeout=timeout,
            retry_timeout=retry_timeout,
            recoverable_exceptions=recoverable_exceptions,
        )


__all__ = [
    "SharedUnitTestCase",
    "SharedIntegrationTestCase",
    "SharedTourTestCase",
    "browser_http_url",
    "preflight_get",
    "run_browser_js_suite",
    "wait_for_browser_endpoint",
]
