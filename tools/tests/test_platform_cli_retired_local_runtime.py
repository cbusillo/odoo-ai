import unittest
from typing import Any

from click.testing import CliRunner

from tools.platform import cli

platform_cli_command: Any = cli.main


class PlatformCliRetiredLocalRuntimeTests(unittest.TestCase):
    def test_manifest_backed_replacements_are_reported_for_supported_commands(self) -> None:
        runner = CliRunner()

        replacement_by_command = {
            "select": "uv --directory /path/to/odoo-devkit run platform runtime select --manifest /path/to/workspace.toml",
            "up": "uv --directory /path/to/odoo-devkit run platform runtime up --manifest /path/to/workspace.toml --build",
            "inspect": "uv --directory /path/to/odoo-devkit run platform runtime inspect --manifest /path/to/workspace.toml",
            "init": "uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow init",
            "update": "uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow update",
            "openupgrade": "uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow openupgrade",
        }

        for command_name, replacement_command in replacement_by_command.items():
            with self.subTest(command_name=command_name):
                result = runner.invoke(platform_cli_command, [command_name, "--context", "cm"])
                self.assertEqual(result.exit_code, 1, msg=result.output)
                self.assertIn(f"'platform {command_name}' is retired in odoo-ai.", result.output)
                self.assertIn(replacement_command, result.output)

    def test_local_destructive_data_workflows_require_explicit_instance(self) -> None:
        runner = CliRunner()

        command_arguments_by_name = {
            "restore": ["restore", "--context", "cm"],
            "bootstrap": ["bootstrap", "--context", "cm"],
        }

        for command_name, command_arguments in command_arguments_by_name.items():
            with self.subTest(command_name=command_name):
                result = runner.invoke(platform_cli_command, command_arguments)
                self.assertEqual(result.exit_code, 2, msg=result.output)
                self.assertIn("Missing option '--instance'", result.output)

    def test_repo_local_helpers_fail_closed_without_replacement_claims(self) -> None:
        runner = CliRunner()

        for command_name, extra_args in (
            ("down", []),
            ("logs", []),
            ("build", ["--stack-file", "platform/stack.toml"]),
            ("odoo-shell", ["--stack-file", "platform/stack.toml", "--script", "tmp/scripts/example.py"]),
        ):
            with self.subTest(command_name=command_name):
                result = runner.invoke(platform_cli_command, [command_name, "--context", "cm", *extra_args])
                self.assertEqual(result.exit_code, 1, msg=result.output)
                self.assertIn(f"'platform {command_name}' is retired in odoo-ai.", result.output)
                self.assertIn("no longer has a supported home in odoo-ai", result.output)

    def test_retired_odoo_shell_shim_reaches_handoff_without_script_argument(self) -> None:
        runner = CliRunner()

        result = runner.invoke(platform_cli_command, ["odoo-shell", "--context", "cm"])

        self.assertEqual(result.exit_code, 1, msg=result.output)
        self.assertIn("'platform odoo-shell' is retired in odoo-ai.", result.output)
        self.assertIn("no longer has a supported home in odoo-ai", result.output)

    def test_tui_does_not_advertise_retired_local_runtime_workflows(self) -> None:
        runner = CliRunner()

        for retired_workflow in ("up", "init", "update", "openupgrade"):
            with self.subTest(retired_workflow=retired_workflow):
                result = runner.invoke(platform_cli_command, ["tui", "--workflow", retired_workflow])

                self.assertEqual(result.exit_code, 2, msg=result.output)
                self.assertIn("Invalid value for '--workflow'", result.output)

    def test_run_does_not_accept_retired_repo_local_workflows(self) -> None:
        runner = CliRunner()

        for retired_workflow in ("init", "update", "openupgrade"):
            with self.subTest(retired_workflow=retired_workflow):
                result = runner.invoke(platform_cli_command, ["run", "--context", "cm", "--workflow", retired_workflow])

                self.assertEqual(result.exit_code, 2, msg=result.output)
                self.assertIn("Invalid value for '--workflow'", result.output)

    def test_run_restore_and_bootstrap_require_explicit_instance(self) -> None:
        runner = CliRunner()

        command_arguments_by_name = {
            "run": ["run", "--context", "cm", "--workflow", "restore"],
            "restore": ["restore", "--context", "cm"],
            "bootstrap": ["bootstrap", "--context", "cm"],
        }

        for command_name, command_arguments in command_arguments_by_name.items():
            with self.subTest(command_name=command_name):
                result = runner.invoke(platform_cli_command, command_arguments)

                self.assertEqual(result.exit_code, 2, msg=result.output)
                self.assertIn("Missing option '--instance'", result.output)

    def test_tui_retires_local_restore_target(self) -> None:
        runner = CliRunner()

        result = runner.invoke(
            platform_cli_command,
            ["tui", "--context", "cm", "--instance", "local", "--workflow", "restore", "--json"],
        )

        self.assertEqual(result.exit_code, 1, msg=result.output)
        self.assertIn("'platform restore' is retired in odoo-ai.", result.output)
        self.assertIn("--instance local", result.output)

    def test_restore_and_bootstrap_retire_remote_instances_too(self) -> None:
        runner = CliRunner()

        command_arguments_by_name = {
            "restore": ["restore", "--context", "cm", "--instance", "testing"],
            "bootstrap": ["bootstrap", "--context", "cm", "--instance", "testing"],
            "run": ["run", "--context", "cm", "--instance", "testing", "--workflow", "restore"],
        }

        for command_name, command_arguments in command_arguments_by_name.items():
            with self.subTest(command_name=command_name):
                result = runner.invoke(platform_cli_command, command_arguments)

                self.assertEqual(result.exit_code, 1, msg=result.output)
                self.assertIn("retired in odoo-ai", result.output)
                self.assertIn("--instance testing", result.output)


if __name__ == "__main__":
    unittest.main()
