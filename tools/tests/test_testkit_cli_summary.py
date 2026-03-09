"""Regression tests for testkit CLI and validation summaries."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.testkit.cli import _host_resources_from_run_plan, _outcome_kinds_from_summary, _top_failure_reasons
from tools.testkit.summary_helpers import host_resources_from_run_plan, outcome_kinds_from_results, phase_outcome_kinds_from_results
from tools.testkit.validate import _outcome_kinds_summary, _run_plan_host_resources


class TestkitCliSummaryTests(unittest.TestCase):
    def test_outcome_kinds_from_summary_aggregates_phase_totals(self) -> None:
        summary_data: dict[str, object] = {
            "results": {
                "unit": {"outcome_kinds": {"test_failure": 1}},
                "tour": {"outcome_kinds": {"infra_failure": 2, "test_failure": 1}},
            }
        }

        self.assertEqual(
            _outcome_kinds_from_summary(summary_data),
            {"infra_failure": 2, "test_failure": 2},
        )
        results: dict[str, object] = {
            "unit": {"outcome_kinds": {"test_failure": 1}},
            "tour": {"outcome_kinds": {"infra_failure": 2, "test_failure": 1}},
        }
        self.assertEqual(
            outcome_kinds_from_results(results),
            {"infra_failure": 2, "test_failure": 2},
        )

    def test_top_failure_reasons_counts_shard_reason_frequency(self) -> None:
        phases: dict[str, object] = {
            "unit": {
                "shard_summaries": [
                    {"failure_reasons": ["reported_test_failures", "timed_out"]},
                    {"failure_reasons": ["reported_test_failures"]},
                ]
            },
            "tour": {"shard_summaries": [{"failure_reasons": ["timed_out"]}]},
        }

        self.assertEqual(
            _top_failure_reasons(phases),
            {"reported_test_failures": 2, "timed_out": 2},
        )

    def test_host_resources_helpers_read_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            (session_dir / "run-plan.json").write_text(
                json.dumps({"host_resources": {"browser_slots": 1, "production_clone_slots": 2}})
            )
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "results": {
                            "unit": {"outcome_kinds": {"test_failure": 1}},
                            "tour": {"outcome_kinds": {"infra_failure": 1}},
                        }
                    }
                )
            )

            self.assertEqual(_run_plan_host_resources(session_dir), {"browser_slots": 1, "production_clone_slots": 2})
            self.assertEqual(_outcome_kinds_summary(session_dir), {"unit": {"test_failure": 1}, "tour": {"infra_failure": 1}})
            self.assertEqual(
                phase_outcome_kinds_from_results(
                    {
                        "unit": {"outcome_kinds": {"test_failure": 1}},
                        "tour": {"outcome_kinds": {"infra_failure": 1}},
                    }
                ),
                {"unit": {"test_failure": 1}, "tour": {"infra_failure": 1}},
            )

        self.assertEqual(
            _host_resources_from_run_plan({"host_resources": {"browser_slots": 1, "production_clone_slots": 2}}),
            {"browser_slots": 1, "production_clone_slots": 2},
        )
        self.assertEqual(
            host_resources_from_run_plan({"host_resources": {"browser_slots": 1, "production_clone_slots": 2}}),
            {"browser_slots": 1, "production_clone_slots": 2},
        )


if __name__ == "__main__":
    unittest.main()
