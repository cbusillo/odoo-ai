"""Integration-style tests for platform CLI TUI wiring."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from tools.platform import cli
from tools.platform.models import ContextDefinition, InstanceDefinition, LoadedStack, StackDefinition

platform_cli_command: Any = cli.main


def _sample_stack_definition() -> StackDefinition:
    return StackDefinition(
        schema_version=1,
        odoo_version="19.0",
        addons_path=("/odoo/addons",),
        contexts={
            "cm": ContextDefinition(
                instances={
                    "local": InstanceDefinition(),
                    "testing": InstanceDefinition(),
                }
            ),
            "opw": ContextDefinition(
                instances={
                    "local": InstanceDefinition(),
                }
            ),
        },
    )


class PlatformCliTuiTests(unittest.TestCase):
    def test_tui_command_forwards_explicit_wildcard_options(self) -> None:
        runner = CliRunner()
        with patch("tools.platform.cli.platform_commands_workflow.execute_tui_command") as execute_tui_command_mock:
            result = runner.invoke(
                platform_cli_command,
                [
                    "tui",
                    "--context",
                    "all",
                    "--instance",
                    "local",
                    "--workflow",
                    "status",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        execute_tui_command_mock.assert_called_once()
        command_kwargs = execute_tui_command_mock.call_args.kwargs
        self.assertEqual(command_kwargs["context_name"], "all")
        self.assertEqual(command_kwargs["instance_name"], "local")
        self.assertEqual(command_kwargs["workflow"], "status")

    def test_tui_command_forwards_asterisk_wildcard_options(self) -> None:
        runner = CliRunner()
        with patch("tools.platform.cli.platform_commands_workflow.execute_tui_command") as execute_tui_command_mock:
            result = runner.invoke(
                platform_cli_command,
                [
                    "tui",
                    "--context",
                    "*",
                    "--instance",
                    "*",
                    "--workflow",
                    "status",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        execute_tui_command_mock.assert_called_once()
        command_kwargs = execute_tui_command_mock.call_args.kwargs
        self.assertEqual(command_kwargs["context_name"], "*")
        self.assertEqual(command_kwargs["instance_name"], "*")
        self.assertEqual(command_kwargs["workflow"], "status")

    def test_tui_command_forwards_comma_selectors(self) -> None:
        runner = CliRunner()
        with patch("tools.platform.cli.platform_commands_workflow.execute_tui_command") as execute_tui_command_mock:
            result = runner.invoke(
                platform_cli_command,
                [
                    "tui",
                    "--context",
                    "cm,opw",
                    "--instance",
                    "local,testing",
                    "--workflow",
                    "info",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        execute_tui_command_mock.assert_called_once()
        command_kwargs = execute_tui_command_mock.call_args.kwargs
        self.assertEqual(command_kwargs["context_name"], "cm,opw")
        self.assertEqual(command_kwargs["instance_name"], "local,testing")
        self.assertEqual(command_kwargs["workflow"], "info")

    def test_tui_command_forwards_json_option(self) -> None:
        runner = CliRunner()
        with patch("tools.platform.cli.platform_commands_workflow.execute_tui_command") as execute_tui_command_mock:
            result = runner.invoke(
                platform_cli_command,
                [
                    "tui",
                    "--context",
                    "all",
                    "--instance",
                    "local",
                    "--workflow",
                    "status",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        execute_tui_command_mock.assert_called_once()
        command_kwargs = execute_tui_command_mock.call_args.kwargs
        self.assertEqual(command_kwargs["json_output"], True)

    def test_tui_command_forwards_json_output_option_alias(self) -> None:
        runner = CliRunner()
        with patch("tools.platform.cli.platform_commands_workflow.execute_tui_command") as execute_tui_command_mock:
            result = runner.invoke(
                platform_cli_command,
                [
                    "tui",
                    "--context",
                    "all",
                    "--instance",
                    "local",
                    "--workflow",
                    "status",
                    "--json-output",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        execute_tui_command_mock.assert_called_once()
        command_kwargs = execute_tui_command_mock.call_args.kwargs
        self.assertEqual(command_kwargs["json_output"], True)

    def test_tui_command_runs_interactive_flow_end_to_end(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")

            loaded_stack = LoadedStack(
                stack_file_path=stack_file_path,
                stack_definition=_sample_stack_definition(),
            )
            captured_run_calls: list[dict[str, object]] = []

            def run_workflow(**kwargs: object) -> None:
                captured_run_calls.append(kwargs)

            runner = CliRunner()
            with (
                patch("tools.platform.cli._discover_repo_root", return_value=repo_root),
                patch("tools.platform.cli._load_stack", return_value=loaded_stack),
                patch("tools.platform.cli._ordered_instance_names", side_effect=lambda context_definition: list(context_definition.instances)),
                patch("tools.platform.cli._run_workflow", side_effect=run_workflow),
                patch("tools.platform.commands_workflow.questionary", None),
            ):
                result = runner.invoke(
                    platform_cli_command,
                    ["tui", "--stack-file", "platform/stack.toml"],
                    input="cm\nstatus\nlocal\n",
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertEqual(len(captured_run_calls), 1)
            self.assertEqual(captured_run_calls[0]["context_name"], "cm")
            self.assertEqual(captured_run_calls[0]["instance_name"], "local")
            self.assertEqual(captured_run_calls[0]["workflow"], "status")


if __name__ == "__main__":
    unittest.main()
