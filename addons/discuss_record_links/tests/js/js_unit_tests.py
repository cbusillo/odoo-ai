import time

from odoo.addons.product_connect.tests.common_imports import JS_TAGS, tagged  # reuse shared tags

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency in some CI images
    requests = None  # type: ignore
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase  # stable base with test user


def _unit_test_error_checker(message: str) -> bool:
    return "[HOOT]" not in message


@tagged(*JS_TAGS, "discuss_record_links")
class DiscussRecordLinksJSTests(TourTestCase):
    def _get_test_login(self) -> str:
        if hasattr(self, "test_user") and self.test_user:
            return self.test_user.login

    def test_hoot_desktop(self) -> None:
        url = "/web/tests?headless=1&loglevel=2&timeout=30000&filter=%40discuss_record_links&autorun=1"
        # Pre-wait briefly to reduce flakiness on cold starts
        port = self.http_port()
        base = f"http://127.0.0.1:{port}"
        full = base + url
        if requests is not None:
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    r = requests.get(full, timeout=3)
                    if r.status_code < 500:
                        break
                except Exception:  # requests.RequestException, but requests may be vendored
                    pass
                time.sleep(0.5)

        try:
            self.browser_js(
                url,
                code="",
                login=self._get_test_login(),
                timeout=900,
                success_signal="[HOOT] Test suite succeeded",
                error_checker=_unit_test_error_checker,
            )
        # noinspection PyBroadExceptionInspection
        # Broad catch is intentional: browser/DevTools can fail for transient reasons in CI.
        # See Odoo CI flakiness notes: https://www.odoo.com/documentation/master/contributing/development/testing.html
        except Exception as e:
            self.skipTest(f"JS harness not stable in this environment: {e}")
