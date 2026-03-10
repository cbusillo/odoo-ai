"""Regression tests for testkit CLI and validation summaries."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

from tools.testkit.cli import _host_resources_from_run_plan, _outcome_kinds_from_summary, _top_failure_reasons
from tools.testkit.cli import test as test_command_group
from tools.testkit.plan import PhaseExecutionPlan, RunExecutionPlan
from tools.testkit.summary_helpers import host_resources_from_run_plan, outcome_kinds_from_results, phase_outcome_kinds_from_results
from tools.testkit.validate import _outcome_kinds_summary, _run_plan_host_resources


def _as_click_command(command: object) -> click.Command:
    assert isinstance(command, click.Command)
    return command


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

    def test_wait_falls_back_to_latest_when_current_pointer_clears(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with chdir(temp_path):
                base_dir = Path("tmp") / "test-logs"
                finished_session = base_dir / "test-20260309_181054"
                finished_session.mkdir(parents=True, exist_ok=True)
                (finished_session / "summary.json").write_text(json.dumps({"success": True}), encoding="utf-8")

                pending_session = base_dir / "pending-session"
                pending_session.mkdir(parents=True, exist_ok=True)
                current_pointer = base_dir / "current"
                latest_pointer = base_dir / "latest"
                current_pointer.symlink_to(pending_session.name)
                latest_pointer.symlink_to(finished_session.name)

                def _clear_current(_seconds: int) -> None:
                    current_pointer.unlink()

                with patch("time.sleep", side_effect=_clear_current):
                    result = runner.invoke(
                        _as_click_command(test_command_group),
                        ["wait", "--timeout", "2", "--interval", "1", "--json"],
                        catch_exceptions=False,
                    )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            json.loads(result.output),
            {
                "success": True,
                "summary": str((temp_path / finished_session / "summary.json").resolve()),
            },
        )

    def test_plan_overlap_flag_enables_parallel_phase_groups(self) -> None:
        runner = CliRunner()

        class _FakeSession:
            @staticmethod
            def build_run_plan() -> RunExecutionPlan:
                self_overlap = os.environ.get("PHASES_OVERLAP")
                assert self_overlap == "1"
                phase_groups = (("unit", "js"), ("integration", "tour"))
                phases = tuple(
                    PhaseExecutionPlan(
                        phase=phase_name,
                        modules=(f"{phase_name}_module",),
                        timeout=1200,
                        strategy="lpt_v1",
                        requested_shards=1,
                        effective_shards=1,
                        max_workers=1,
                        template_strategy="production" if phase_name in {"integration", "tour"} else "phase",
                        uses_browser=phase_name in {"js", "tour"},
                        uses_production_clone=phase_name in {"integration", "tour"},
                        module_shards=((f"{phase_name}_module",),),
                    )
                    for phase_name in ("unit", "js", "integration", "tour")
                )
                return RunExecutionPlan(
                    phases=phases,
                    phase_groups=phase_groups,
                    overlap_enabled=True,
                    browser_slots=1,
                    production_clone_slots=2,
                )

        with patch.dict(os.environ, {}):
            with (
                patch("tools.testkit.cli._apply_stack_env"),
                patch("tools.testkit.cli._build_session", return_value=_FakeSession()),
            ):
                result = runner.invoke(
                    _as_click_command(test_command_group),
                    ["plan", "--stack", "opw", "--phase", "all", "--json", "--overlap"],
                    catch_exceptions=False,
                )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.output)
        self.assertTrue(payload["overlap_enabled"])
        self.assertEqual(payload["phase_groups"], [["unit", "js"], ["integration", "tour"]])


if __name__ == "__main__":
    unittest.main()
