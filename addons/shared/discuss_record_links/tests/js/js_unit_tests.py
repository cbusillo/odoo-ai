from ..common_imports import common
from ..fixtures.base import TourTestCase


def _unit_test_error_checker(message: str) -> bool:
    return "[HOOT]" not in message


@common.tagged(*common.JS_TAGS, "discuss_record_links")
class DiscussRecordLinksJSTests(TourTestCase):
    def _get_test_login(self) -> str:
        if hasattr(self, "test_user") and self.test_user and self.test_user.login:
            return self.test_user.login
        return "tour_test_user"

    def test_hoot_desktop(self) -> None:
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%40discuss_record_links&autorun=1"
        self.run_browser_js_suite(
            url,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=_unit_test_error_checker,
            recoverable_exceptions=(AssertionError,),
        )
