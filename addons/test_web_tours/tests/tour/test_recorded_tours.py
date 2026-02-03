import json
import logging
from collections.abc import Sequence
import os
from pathlib import Path

from odoo.tests import HttpCase, tagged

_logger = logging.getLogger(__name__)

TOUR_PREFIX = "test_"
DEFAULT_START_URL = "/web"


@tagged("post_install", "-at_install", "tour_test", "test_web_tours")
class TestRecordedDbTours(HttpCase):
    """Execute recorded tours stored in the database whose name starts with ``test_``."""
    _recorded_tours_enabled: bool = False

    @staticmethod
    def _normalize_steps(steps_payload: Sequence[dict[str, object]] | str) -> list[dict[str, object]]:
        decoded: object = steps_payload
        if isinstance(steps_payload, str):
            try:
                decoded = json.loads(steps_payload)
            except json.JSONDecodeError:
                return []
        if not isinstance(decoded, list):
            return []
        return [step for step in decoded if isinstance(step, dict)]

    @classmethod
    def _load_fixture_entries(cls) -> list[dict[str, object]]:
        raw_json = os.environ.get("RECORDED_TOURS_JSON")
        if raw_json:
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError as error:
                _logger.warning("Invalid RECORDED_TOURS_JSON payload (%s)", error)
                return []
            if not isinstance(payload, list):
                _logger.warning("RECORDED_TOURS_JSON must be a list; got %s", type(payload).__name__)
                return []
            return [entry for entry in payload if isinstance(entry, dict)]

        recorded_tours_path = os.environ.get("RECORDED_TOURS_PATH")
        if not recorded_tours_path:
            _logger.info("No recorded tour source configured (RECORDED_TOURS_JSON/PATH)")
            return []
        try:
            payload = json.loads(Path(recorded_tours_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _logger.warning("Failed to read recorded tour fixture at %s (%s)", recorded_tours_path, error)
            return []
        if not isinstance(payload, list):
            _logger.warning("Recorded tour fixture must be a list; got %s", type(payload).__name__)
            return []
        return [entry for entry in payload if isinstance(entry, dict)]

    @classmethod
    def _seed_recorded_tours(cls) -> None:
        entries = cls._load_fixture_entries()
        if not entries:
            return

        tour_model = cls.env["web_tour.tour"]
        step_model = cls.env["web_tour.tour.step"]

        created_tours = 0
        created_steps = 0

        for entry in entries:
            raw_name = entry.get("name")
            if not isinstance(raw_name, str) or not raw_name.startswith(TOUR_PREFIX):
                continue
            tour_name = raw_name
            existing = tour_model.search([("name", "=", tour_name)], limit=1)
            if existing and not getattr(existing, "custom", False):
                tour_name = f"{tour_name}__recorded_db"
                existing = tour_model.search([("name", "=", tour_name)], limit=1)

            tour = existing
            if not tour:
                values = {
                    "name": tour_name,
                    "url": entry.get("url") or DEFAULT_START_URL,
                }
                if "custom" in tour_model._fields:
                    values["custom"] = True
                tour = tour_model.create(values)
                created_tours += 1

            if tour.step_ids:
                continue

            steps_payload = entry.get("steps")
            steps = steps_payload if isinstance(steps_payload, list) else []
            step_vals: list[dict[str, object]] = []
            for step_index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                trigger_value = step.get("trigger")
                if not isinstance(trigger_value, str) or not trigger_value:
                    continue
                sequence_value = step.get("sequence")
                if not isinstance(sequence_value, int):
                    sequence_value = step_index
                step_vals.append(
                    {
                        "tour_id": tour.id,
                        "sequence": sequence_value,
                        "trigger": trigger_value,
                        "content": step.get("content"),
                        "run": step.get("run"),
                        "tooltip_position": step.get("tooltip_position"),
                    }
                )
            if step_vals:
                step_model.create(step_vals)
                created_steps += len(step_vals)

        if created_tours or created_steps:
            _logger.info("Seeded recorded tours: %s tours, %s steps", created_tours, created_steps)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._recorded_tours_enabled = os.environ.get("RECORDED_TOURS_ENABLE") == "1"
        if not cls._recorded_tours_enabled:
            cls._tours = cls.env["web_tour.tour"].browse([])
            return
        cls._seed_recorded_tours()
        tour_model = cls.env["web_tour.tour"]
        domain = [("name", "ilike", f"{TOUR_PREFIX}%"), ("step_ids", "!=", False)]
        if "custom" in tour_model._fields:
            domain.append(("custom", "=", True))
        cls._tours = tour_model.search(domain)
        _logger.info("Discovered recorded tours with steps: %s", cls._tours.mapped("name"))

    def _inject_tour(self, name: str, steps: Sequence[dict[str, object]]) -> str:
        steps_js = json.dumps(list(steps))
        injected_name = f"{name}__recorded_db"
        code = f"""
            const steps = {steps_js};
            const registryModule = window.odoo?.loader?.modules?.get("@web/core/registry");
            const registry = registryModule?.registry || odoo.registry;
            if (!registry) {{
                throw new Error("test_web_tours: registry not available");
            }}
            const tourCategory = registry.category("web_tour.tours");
            if (tourCategory.contains?.("{injected_name}")) {{
                tourCategory.remove?.("{injected_name}");
            }}
            tourCategory.add("{injected_name}", {{
                test: true,
                steps: () => steps,
            }});
        """
        self.browser_js(DEFAULT_START_URL, code, login="admin", timeout=180)
        return injected_name

    def test_recorded_db_tours(self) -> None:
        if not self._recorded_tours_enabled:
            self.skipTest("Recorded DB tours disabled (set RECORDED_TOURS_ENABLE=1 to run)")
        if not self._tours:
            self.skipTest("No recorded web tours with steps found for test_ prefix")

        executed_count = 0

        for tour in self._tours:
            steps = self._normalize_steps(tour.step_ids.get_steps_json())
            if not steps:
                _logger.warning("Skipping recorded tour %s: no steps found", tour.name)
                continue

            start_url = tour.url or DEFAULT_START_URL
            injected_tour_name = self._inject_tour(tour.name, steps)
            self.start_tour(start_url, injected_tour_name, login="admin")
            executed_count += 1

        if executed_count == 0:
            self.skipTest("All discovered recorded tours were empty or invalid")
