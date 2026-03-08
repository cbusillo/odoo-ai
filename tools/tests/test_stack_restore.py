"""Regression tests for restore environment propagation behavior."""

from __future__ import annotations

import os
import unittest

from tools import stack_restore


class StackRestoreTests(unittest.TestCase):
    def test_restore_script_environment_keeps_required_keys_and_prefixes(self) -> None:
        env_values = {
            "ODOO_DB_PASSWORD": "secret",
            "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
            "ENV_OVERRIDE_DISABLE_CRON": "true",
            "OPENUPGRADE_FORCE": "1",
            "UNRELATED": "drop-me",
        }

        filtered_values = stack_restore._restore_script_environment(env_values)

        self.assertEqual(
            filtered_values,
            {
                "ODOO_DB_PASSWORD": "secret",
                "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
                "ENV_OVERRIDE_DISABLE_CRON": "true",
                "OPENUPGRADE_FORCE": "1",
            },
        )

    def test_add_exec_env_names_uses_name_only_flags(self) -> None:
        command = ["docker", "compose", "exec"]

        stack_restore._add_exec_env_names(command, ["ODOO_DB_PASSWORD", "ODOO_FILESTORE_PATH"])

        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "exec",
                "-e",
                "ODOO_DB_PASSWORD",
                "-e",
                "ODOO_FILESTORE_PATH",
            ],
        )

    def test_resolve_restore_environment_uses_process_env_for_missing_variable_references(self) -> None:
        previous_value = os.environ.get("RESTORE_TEST_SENTINEL")
        os.environ["RESTORE_TEST_SENTINEL"] = "host-value"
        try:
            resolved = stack_restore._resolve_restore_environment(
                {
                    "FROM_DEFAULT": "${RESTORE_TEST_SENTINEL:-fallback}",
                    "CHAINED": "${FROM_DEFAULT}",
                }
            )
        finally:
            if previous_value is None:
                os.environ.pop("RESTORE_TEST_SENTINEL", None)
            else:
                os.environ["RESTORE_TEST_SENTINEL"] = previous_value

        self.assertEqual(resolved["FROM_DEFAULT"], "host-value")
        self.assertEqual(resolved["CHAINED"], "host-value")

    def test_resolve_restore_environment_uses_default_when_process_env_missing(self) -> None:
        previous_value = os.environ.get("RESTORE_TEST_MISSING")
        os.environ.pop("RESTORE_TEST_MISSING", None)
        try:
            resolved = stack_restore._resolve_restore_environment(
                {
                    "FROM_DEFAULT": "${RESTORE_TEST_MISSING:-fallback}",
                    "CHAINED": "${FROM_DEFAULT}",
                }
            )
        finally:
            if previous_value is None:
                os.environ.pop("RESTORE_TEST_MISSING", None)
            else:
                os.environ["RESTORE_TEST_MISSING"] = previous_value

        self.assertEqual(resolved["FROM_DEFAULT"], "fallback")
        self.assertEqual(resolved["CHAINED"], "fallback")

    def test_resolve_restore_environment_substitutes_known_variables(self) -> None:
        resolved = stack_restore._resolve_restore_environment(
            {
                "BASE": "odoo",
                "IMAGE": "${BASE}:19",
            }
        )

        self.assertEqual(resolved["IMAGE"], "odoo:19")

    def test_resolve_restore_environment_expands_dollar_style_env_variables(self) -> None:
        previous_value = os.environ.get("RESTORE_LEGACY_PATH")
        os.environ["RESTORE_LEGACY_PATH"] = "/tmp/legacy-restore"
        try:
            resolved = stack_restore._resolve_restore_environment(
                {
                    "FROM_SHELL_STYLE": "$RESTORE_LEGACY_PATH/filestore",
                }
            )
        finally:
            if previous_value is None:
                os.environ.pop("RESTORE_LEGACY_PATH", None)
            else:
                os.environ["RESTORE_LEGACY_PATH"] = previous_value

        self.assertEqual(resolved["FROM_SHELL_STYLE"], "/tmp/legacy-restore/filestore")

    def test_resolve_restore_environment_expands_home_directory_shorthand(self) -> None:
        resolved = stack_restore._resolve_restore_environment(
            {
                "HOME_STYLE_PATH": "~/restore-input",
            }
        )

        self.assertEqual(
            resolved["HOME_STYLE_PATH"],
            os.path.expanduser("~/restore-input"),
        )

    def test_missing_upstream_restore_keys_reports_only_empty_required_values(self) -> None:
        missing_keys = stack_restore._missing_upstream_restore_keys(
            {
                "ODOO_UPSTREAM_HOST": "source.example.com",
                "ODOO_UPSTREAM_USER": "",
                "ODOO_UPSTREAM_DB_NAME": "upstream",
                "ODOO_UPSTREAM_DB_USER": "   ",
                "ODOO_UPSTREAM_FILESTORE_PATH": "/opt/odoo/.local/share/Odoo/filestore/upstream",
            }
        )

        self.assertEqual(
            missing_keys,
            (
                "ODOO_UPSTREAM_USER",
                "ODOO_UPSTREAM_DB_USER",
            ),
        )


if __name__ == "__main__":
    unittest.main()
