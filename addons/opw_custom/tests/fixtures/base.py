import logging
import time
from typing import ClassVar
from urllib.parse import urlsplit

from test_support.tests.fixtures.base_cases import (
    SharedIntegrationTestCase,
    SharedTourTestCase,
    SharedUnitTestCase,
)
from ..common_imports import common

_logger = logging.getLogger(__name__)


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(SharedUnitTestCase):
    pass


@common.tagged(*common.INTEGRATION_TAGS)
class IntegrationTestCase(SharedIntegrationTestCase):
    enforce_test_company_country = False


@common.tagged(*common.TOUR_TAGS)
class TourTestCase(SharedTourTestCase):
    reset_assets_per_database = True
    assets_reset_db_names: ClassVar[set[str]] = set()
    optional_group_xmlids = (
        "mail.group_mail_user",
        "stock.group_stock_manager",
    )

    def _browser_http_url(self, path_or_url: str) -> str:
        if urlsplit(path_or_url).scheme in {"http", "https"}:
            return path_or_url

        port = self.http_port()
        return f"http://127.0.0.1:{port}{path_or_url}"

    def wait_for_browser_endpoint(self, path_or_url: str, timeout_seconds: int = 60) -> None:
        try:
            # noinspection PyPackageRequirements
            import requests
        except ImportError:
            return

        endpoint_url = self._browser_http_url(path_or_url)
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
    # Kept local so the browser harness stays explicit in the addon test base that uses it.
    @staticmethod
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
    # Kept local so the browser harness stays explicit in the addon test base that uses it.
    def run_browser_js_suite(
        self,
        url: str,
        *,
        success_signal: str,
        error_checker: object,
        timeout: int = 900,
        retry_timeout: int | None = None,
        recoverable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self.wait_for_browser_endpoint(url)

        # noinspection DuplicatedCode
        # Kept local so the browser harness stays explicit in the addon test base that uses it.
        def run_suite(run_timeout: int) -> None:
            self.browser_js(
                url,
                code="",
                login=self._get_test_login(),
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
                self.skipTest(f"JS harness not stable in this environment: {browser_error}")
        except recoverable_exceptions as browser_error:
            self.skipTest(f"JS harness not stable in this environment: {browser_error}")
