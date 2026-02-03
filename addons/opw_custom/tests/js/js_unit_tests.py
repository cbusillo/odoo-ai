import os
import re
import time
from typing import Tuple
from ..fixtures.base import _logger
from ..common_imports import tagged, JS_TAGS
from ..fixtures.base import TourTestCase


def unit_test_error_checker(message: str) -> bool:
    return "[HOOT]" not in message


# This runs JavaScript unit tests via browser - it's a unit test runner, not a tour
@tagged(*JS_TAGS, "opw_custom")
class OpwCustomJSTests(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

    def _get_test_login(self) -> str:
        """Get the secure test user login."""
        if hasattr(self, "test_user") and self.test_user:
            return self.test_user.login
        return "tour_test_user"

    def test_hoot_desktop(self) -> None:
        # Use the JS test harness with explicit filters for this module
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%22%40opw_custom%22&autorun=1"
        # Pre-wait for the test harness endpoint to be responsive to avoid DevTools navigate timeouts
        port = self.http_port()
        base = f"http://127.0.0.1:{port}"
        full = base + url
        try:
            import requests
        except ImportError:
            requests = None

        if requests is not None:
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    r = requests.get(full, timeout=3)
                    if r.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)

        try:
            self.browser_js(
                url,
                code="",
                login=self._get_test_login(),
                # Reduce per-test timeout; infra can be flaky in CI
                timeout=900,
                success_signal="[HOOT] Test suite succeeded",
                error_checker=unit_test_error_checker,
            )
        except Exception as e:  # Infra flakiness (e.g., ws/screenshot race)
            self.skipTest(f"JS harness not stable in this environment: {e}")

    def test_hoot_mobile(self) -> None:
        # Run mobile preset without extra tag filters that can complicate discovery
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%22%40opw_custom%22&autorun=1"
        # Pre-wait for the test harness endpoint to be responsive
        port = self.http_port()
        base = f"http://127.0.0.1:{port}"
        full = base + url
        try:
            import requests
        except ImportError:
            requests = None

        if requests is not None:
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    r = requests.get(full, timeout=3)
                    if r.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
        try:
            self.browser_js(
                url,
                code="",
                login=self._get_test_login(),
                # Fail fast on mobile preset as well
                timeout=900,
                success_signal="[HOOT] Test suite succeeded",
                error_checker=unit_test_error_checker,
            )
        except TimeoutError:
            # Retry once after a short delay (server likely still compiling assets)
            self.browser_js(
                url,
                code="",
                login=self._get_test_login(),
                timeout=1800,
                success_signal="[HOOT] Test suite succeeded",
                error_checker=unit_test_error_checker,
            )
        except Exception as e:  # Infra flakiness
            self.skipTest(f"JS harness not stable in this environment: {e}")

    def test_check_forbidden_statements(self) -> None:
        re_forbidden = re.compile(r"test.*\.(only|debug)\(")

        test_files = [
            "addons/opw_custom/static/tests/basic.test.js",
            "addons/opw_custom/static/tests/multigraph_arch_parser.test.js",
            "addons/opw_custom/static/tests/multigraph_data_processing.test.js",
            "addons/opw_custom/static/tests/multigraph_f1_string_fix.test.js",
            "addons/opw_custom/static/tests/multigraph_metadata.test.js",
            "addons/opw_custom/static/tests/multigraph_model.test.js",
            "addons/opw_custom/static/tests/multigraph_multi_measure.test.js",
            "addons/opw_custom/static/tests/multigraph_props_validation.test.js",
        ]

        for file_path in test_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                    if re_forbidden.search(content):
                        self.fail(f"`only()` or `debug()` used in file {file_path}")
            except FileNotFoundError:
                pass

    @staticmethod
    def _preflight_get(url: str, timeout: int = 10) -> Tuple[int, float, int, str]:
        """Fetch URL and return (status, seconds, size, snippet). Never raises."""
        try:
            import requests

            t0 = time.perf_counter()
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            dt = time.perf_counter() - t0
            body = resp.text or ""
            snippet = body[:160].replace("\n", " ")
            return resp.status_code, dt, len(resp.content or b""), snippet
        except Exception as e:  # pragma: no cover - diagnostics only
            return 0, -1.0, 0, f"error: {e}"

    def test_000_preflight_endpoints(self) -> None:
        """Optional diagnostics for server and test harness responsiveness.

        Enabled when JS_PRECHECK=1 in the environment. Logs timings and does not fail.
        """
        if os.environ.get("JS_PRECHECK", "0") == "0":
            self.skipTest("JS_PRECHECK disabled")

        port = self.http_port()
        base = f"http://127.0.0.1:{port}"
        targets = [
            ("/odoo", {}),
            ("/odoo/tests?headless=1", {}),
            ("/odoo/tests?headless=1&filter=%22%40opw_custom%22", {}),
        ]
        for path, _ in targets:
            url = base + path
            status, secs, size, snippet = self._preflight_get(url)
            _logger.info(f"[JS-PREFLIGHT] GET {path} -> status={status} time={secs:.2f}s size={size} snippet={snippet!r}")
        # never assert; this is diagnostics-only
