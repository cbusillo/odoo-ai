"""Regression tests for testkit executor secret redaction."""

from __future__ import annotations

import unittest

from tools.testkit.executor import (
    ShardRuntimeResult,
    _classify_outcome,
    _redact_assignment_token,
    _redact_command_for_logging,
    _sanitize_database_flags_for_summary,
)


class TestkitExecutorRedactionTests(unittest.TestCase):
    def test_redact_assignment_token_redacts_password_values(self) -> None:
        self.assertEqual(_redact_assignment_token("--db_password=secret"), "--db_password=***")
        self.assertEqual(_redact_assignment_token("ODOO_DB_PASSWORD=secret"), "ODOO_DB_PASSWORD=***")
        self.assertEqual(_redact_assignment_token("--db_user=odoo"), "--db_user=odoo")

    def test_redact_command_for_logging_redacts_environment_and_flags(self) -> None:
        command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "-e",
            "ODOO_DB_PASSWORD=secret",
            "script-runner",
            "/odoo/odoo-bin",
            "--db_password=secret",
            "--db_user=odoo",
        ]

        redacted_command = _redact_command_for_logging(command)

        self.assertIn("ODOO_DB_PASSWORD=***", redacted_command)
        self.assertIn("--db_password=***", redacted_command)
        self.assertIn("--db_user=odoo", redacted_command)
        self.assertNotIn("ODOO_DB_PASSWORD=secret", redacted_command)
        self.assertNotIn("--db_password=secret", redacted_command)

    def test_sanitize_database_flags_for_summary_redacts_password_only(self) -> None:
        database_flags = [
            "--db_host=database",
            "--db_port=5432",
            "--db_user=odoo",
            "--db_password=secret",
        ]

        sanitized_flags = _sanitize_database_flags_for_summary(database_flags)

        self.assertEqual(
            sanitized_flags,
            [
                "--db_host=database",
                "--db_port=5432",
                "--db_user=odoo",
                "--db_password=***",
            ],
        )

    def test_classify_outcome_marks_missing_tests_as_harness_failure(self) -> None:
        runtime = ShardRuntimeResult(
            returncode=0,
            counters={"tests_run": 0, "failures": 0, "errors": 0, "skips": 0},
        )

        outcome = _classify_outcome(runtime, expected_tests=3)

        self.assertEqual(outcome.outcome_kind, "harness_failure")
        self.assertEqual(outcome.returncode, 1)
        self.assertEqual(outcome.failure_reasons, ("missing_expected_tests",))
        self.assertEqual(outcome.missing_tests, 3)

    def test_classify_outcome_marks_reported_failures_as_test_failure(self) -> None:
        runtime = ShardRuntimeResult(
            returncode=1,
            counters={"tests_run": 8, "failures": 1, "errors": 0, "skips": 0},
        )

        outcome = _classify_outcome(runtime, expected_tests=8)

        self.assertEqual(outcome.outcome_kind, "test_failure")
        self.assertEqual(outcome.failure_reasons, ("reported_test_failures",))
        self.assertEqual(outcome.returncode, 1)

    def test_classify_outcome_marks_timeouts_without_test_signal_as_infra_failure(self) -> None:
        runtime = ShardRuntimeResult(
            returncode=1,
            counters={"tests_run": 0, "failures": 0, "errors": 0, "skips": 0},
            timed_out=True,
        )

        outcome = _classify_outcome(runtime, expected_tests=0)

        self.assertEqual(outcome.outcome_kind, "infra_failure")
        self.assertEqual(outcome.failure_reasons, ("timed_out", "nonzero_exit_without_test_counters"))

    def test_classify_outcome_prioritizes_harness_failures_over_test_signal(self) -> None:
        runtime = ShardRuntimeResult(
            returncode=1,
            counters={"tests_run": 4, "failures": 1, "errors": 0, "skips": 0},
            default_database_target=True,
        )

        outcome = _classify_outcome(runtime, expected_tests=4)

        self.assertEqual(outcome.outcome_kind, "harness_failure")
        self.assertEqual(outcome.failure_reasons, ("default_database_target", "reported_test_failures"))


if __name__ == "__main__":
    unittest.main()
