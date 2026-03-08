"""Regression tests for testkit DB helpers."""

from __future__ import annotations

import shlex
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.testkit.db import (
    assert_no_default_database_target,
    build_module_template,
    clone_production_database,
    create_template_from_production,
    resolve_database_connection_flags,
)


class TestkitDatabaseHelpersTests(unittest.TestCase):
    def test_resolve_database_connection_flags_uses_environment_values(self) -> None:
        flags = resolve_database_connection_flags(
            {
                "ODOO_DB_HOST": "database.internal",
                "ODOO_DB_PORT": "5434",
                "ODOO_DB_USER": "test_runner",
                "ODOO_DB_PASSWORD": "secret",
            }
        )

        self.assertEqual(
            flags,
            [
                "--db_host=database.internal",
                "--db_port=5434",
                "--db_user=test_runner",
                "--db_password=secret",
            ],
        )

    def test_assert_no_default_database_target_raises_for_default_marker(self) -> None:
        with self.assertRaises(RuntimeError):
            assert_no_default_database_target(
                "database: default@default:default",
                command_name="template build",
            )

    def test_build_module_template_adds_database_flags(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            log_path = Path(temporary_directory_name) / "template.log"
            command_result = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="template build ok",
                stderr="",
            )

            with (
                patch("tools.testkit.db.ensure_services_up"),
                patch("tools.testkit.db.drop_and_create_test_database"),
                patch("tools.testkit.db.get_script_runner_service", return_value="script-runner"),
                patch(
                    "tools.testkit.db.compose_env",
                    return_value={
                        "ODOO_DB_HOST": "database.internal",
                        "ODOO_DB_PORT": "5434",
                        "ODOO_DB_USER": "test_runner",
                        "ODOO_DB_PASSWORD": "secret",
                    },
                ),
                patch("tools.testkit.db.compose_exec", return_value=command_result) as compose_exec_mock,
            ):
                build_module_template("cm_template", ["opw_custom"], timeout_sec=30, log_path=log_path)

            invoked_command = compose_exec_mock.call_args.args[1]
            self.assertIn("--db_host=database.internal", invoked_command)
            self.assertIn("--db_port=5434", invoked_command)
            self.assertIn("--db_user=test_runner", invoked_command)
            self.assertIn("--db_password=secret", invoked_command)

    def test_build_module_template_fails_closed_on_default_database_target(self) -> None:
        command_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="database: default@default:default",
            stderr="",
        )
        with (
            patch("tools.testkit.db.ensure_services_up"),
            patch("tools.testkit.db.drop_and_create_test_database"),
            patch("tools.testkit.db.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.db.compose_env", return_value={}),
            patch("tools.testkit.db.compose_exec", return_value=command_result),
        ):
            with self.assertRaises(RuntimeError):
                build_module_template("cm_template", ["opw_custom"], timeout_sec=30)

    def test_clone_production_database_quotes_shell_values(self) -> None:
        with (
            patch("tools.testkit.db.wait_for_database_ready"),
            patch("tools.testkit.db.force_drop_database"),
            patch("tools.testkit.db._create_database", return_value=True),
            patch("tools.testkit.db.get_production_db_name", return_value="prod;name"),
            patch("tools.testkit.db.get_db_user", return_value="user with space"),
            patch("tools.testkit.db.get_database_service", return_value="database"),
            patch("tools.testkit.db.compose_exec") as compose_exec_mock,
        ):
            clone_production_database("target;db")

        command = compose_exec_mock.call_args.args[1][2]
        self.assertIn(f"-U {shlex.quote('user with space')}", command)
        self.assertIn(shlex.quote("prod;name"), command)
        self.assertIn(shlex.quote("target;db"), command)

    def test_create_template_from_production_quotes_shell_values(self) -> None:
        with (
            patch("tools.testkit.db.wait_for_database_ready"),
            patch("tools.testkit.db.force_drop_database"),
            patch("tools.testkit.db._create_database", return_value=True),
            patch("tools.testkit.db.get_production_db_name", return_value="prod;name"),
            patch("tools.testkit.db.get_db_user", return_value="user with space"),
            patch("tools.testkit.db.get_database_service", return_value="database"),
            patch("tools.testkit.db.compose_exec") as compose_exec_mock,
        ):
            create_template_from_production("template;db")

        command = compose_exec_mock.call_args.args[1][2]
        self.assertIn(f"-U {shlex.quote('user with space')}", command)
        self.assertIn(shlex.quote("prod;name"), command)
        self.assertIn(shlex.quote("template;db"), command)


if __name__ == "__main__":
    unittest.main()
