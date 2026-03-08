"""Regression tests for testkit session fanout controls."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tools.testkit.session import TestSession


class TestkitSessionFanoutTests(unittest.TestCase):
    def test_tour_phase_uses_tour_max_procs_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TEST_MAX_PROCS": "4",
                "TOUR_MAX_PROCS": "1",
            },
            clear=True,
        ):
            session = TestSession()
            max_workers = session._resolve_phase_max_workers("tour", 5)
            self.assertEqual(max_workers, 1)

    def test_non_tour_phase_uses_global_max_procs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TEST_MAX_PROCS": "3",
                "TOUR_MAX_PROCS": "1",
            },
            clear=True,
        ):
            session = TestSession()
            max_workers = session._resolve_phase_max_workers("unit", 6)
            self.assertEqual(max_workers, 3)

    def test_discover_js_modules_uses_static_test_pattern(self) -> None:
        session = TestSession()
        with patch.object(session, "_manifest_modules", return_value=["shopify_sync"]) as manifest_modules_mock:
            modules = session._discover_js_modules()

        manifest_modules_mock.assert_called_once_with(patterns=["**/static/tests/**/*.test.js"])
        self.assertEqual(modules, ["shopify_sync"])


if __name__ == "__main__":
    unittest.main()
