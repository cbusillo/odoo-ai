"""Regression tests for testkit executor secret redaction."""

from __future__ import annotations

import unittest

from tools.testkit.executor import (
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


if __name__ == "__main__":
    unittest.main()
