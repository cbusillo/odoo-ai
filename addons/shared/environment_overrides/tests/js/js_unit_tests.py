from ..common_imports import common
from test_support.tests.fixtures.base_cases import SharedTourTestCase


def _unit_test_error_checker(message: str) -> bool:
    return "[HOOT]" not in message


@common.tagged(*common.JS_TAGS, "environment_overrides")
class EnvironmentOverridesJSTests(SharedTourTestCase):
    def test_hoot_desktop(self) -> None:
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%40environment_overrides&autorun=1"
        self.run_browser_js_suite(
            url,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=_unit_test_error_checker,
            recoverable_exceptions=(AssertionError,),
        )
