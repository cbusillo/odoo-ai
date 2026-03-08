import os
import re

from ..fixtures.base import _logger
from ..common_imports import common
from ..fixtures.base import TourTestCase


def unit_test_error_checker(message: str) -> bool:
    return "[HOOT]" not in message


# This runs JavaScript unit tests via browser - it's a unit test runner, not a tour
@common.tagged(*common.JS_TAGS, "opw_custom")
class OpwCustomJSTests(TourTestCase):
    def test_hoot_desktop(self) -> None:
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%22%40opw_custom%22&autorun=1"
        self.run_browser_js_suite(
            url,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )

    def test_hoot_mobile(self) -> None:
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%22%40opw_custom%22&autorun=1"
        self.run_browser_js_suite(
            url,
            retry_timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )

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

    def test_000_preflight_endpoints(self) -> None:
        """Optional diagnostics for server and test harness responsiveness.

        Enabled when JS_PRECHECK=1 in the environment. Logs timings and does not fail.
        """
        if os.environ.get("JS_PRECHECK", "0") == "0":
            self.skipTest("JS_PRECHECK disabled")

        targets = [
            "/odoo",
            "/odoo/tests?headless=1",
            "/odoo/tests?headless=1&filter=%22%40opw_custom%22",
        ]
        for path in targets:
            status, secs, size, snippet = self.preflight_get(self._browser_http_url(path))
            _logger.info(f"[JS-PREFLIGHT] GET {path} -> status={status} time={secs:.2f}s size={size} snippet={snippet!r}")
