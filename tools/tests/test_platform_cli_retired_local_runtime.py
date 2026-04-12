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

        result = runner.invoke(platform_cli_command, ["tui", "--workflow", "up"])

        self.assertEqual(result.exit_code, 2, msg=result.output)
        self.assertIn("Invalid value for '--workflow'", result.output)


if __name__ == "__main__":
    unittest.main()
