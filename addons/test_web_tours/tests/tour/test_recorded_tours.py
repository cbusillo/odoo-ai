import json
import logging
from collections.abc import Sequence

from odoo.tests import HttpCase, tagged

_logger = logging.getLogger(__name__)

TOUR_PREFIX = "test_"
DEFAULT_START_URL = "/web"


@tagged("post_install", "-at_install", "tour_test", "test_web_tours")
class TestRecordedDbTours(HttpCase):
    """Execute recorded tours stored in the database whose name starts with ``test_``."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._tours = cls.env["web_tour.tour"].search(
            [
                ("active", "=", True),
                ("name", "ilike", f"{TOUR_PREFIX}%"),
            ]
        )
        _logger.info("Discovered recorded tours: %s", cls._tours.mapped("name"))

    def _inject_tour(self, name: str, steps: Sequence[dict]) -> None:
        steps_js = json.dumps(list(steps))
        code = f"""
            const steps = {steps_js};
            odoo.registry.category("web_tour.tours").add("{name}", {{
                test: true,
                steps: () => steps,
            }});
        """
        self.browser_js(DEFAULT_START_URL, code, login="admin")

    def test_recorded_db_tours(self) -> None:
        if not self._tours:
            self.skipTest("No recorded web tours starting with test_")

        for tour in self._tours:
            try:
                steps = json.loads(tour.steps or "[]")
            except json.JSONDecodeError as exc:
                self.fail(f"Tour {tour.name} has invalid JSON steps: {exc}")

            start_url = tour.url or DEFAULT_START_URL
            self._inject_tour(tour.name, steps)
            self.start_tour(start_url, tour.name, login="admin")
