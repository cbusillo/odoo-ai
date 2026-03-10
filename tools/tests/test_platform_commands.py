"""Regression tests for extracted platform command modules."""

from __future__ import annotations

import json
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest.mock import patch

import click

from tools.platform import (
    command_context,
    commands_core,
    commands_dokploy,
    commands_lifecycle,
    commands_release,
    commands_selection,
    commands_workflow,
    release_workflows,
)
from tools.platform import dokploy as platform_dokploy
from tools.platform.models import (
    ContextDefinition,
    DokploySourceOfTruth,
    DokployTargetDefinition,
    EnvironmentCollision,
    InstanceDefinition,
    JsonObject,
    JsonValue,
    LoadedEnvironment,
    LoadedStack,
    RuntimeSelection,
    StackDefinition,
)


def _sample_stack_definition() -> StackDefinition:
    return StackDefinition(
        schema_version=1,
        odoo_version="19.0",
        addons_path=("/odoo/addons",),
        required_env_keys=("REQUIRED_KEY",),
        contexts={
            "cm": ContextDefinition(
                instances={
                    "local": InstanceDefinition(),
                    "testing": InstanceDefinition(),
                }
            )
        },
    )


def _sample_multi_context_stack_definition() -> StackDefinition:
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


def _sample_runtime_selection(context_name: str = "cm", instance_name: str = "local") -> RuntimeSelection:
    context_definition = ContextDefinition(
        instances={
            "local": InstanceDefinition(),
            "testing": InstanceDefinition(),
        }
    )
    instance_definition = context_definition.instances[instance_name]
    return RuntimeSelection(
        context_name=context_name,
        instance_name=instance_name,
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name="cm",
        project_name=f"odoo-{context_name}-{instance_name}",
        state_path=Path(f"/tmp/{context_name}-{instance_name}"),
        data_mount=Path(f"/tmp/{context_name}-{instance_name}/data"),
        runtime_conf_host_path=Path(f"/tmp/{context_name}-{instance_name}/platform.odoo.conf"),
        data_volume_name=f"{context_name}-{instance_name}-data",
        log_volume_name=f"{context_name}-{instance_name}-logs",
        db_volume_name=f"{context_name}-{instance_name}-db",
        web_host_port=8069,
        longpoll_host_port=8072,
        db_host_port=15432,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=("opw_custom",),
        effective_addon_repositories=("cbusillo/example@main",),
        effective_runtime_env={},
    )


def _build_loaded_stack_for_test(
    repo_root: Path,
    *,
    stack_definition: StackDefinition,
) -> LoadedStack:
    stack_file_path = repo_root / "platform" / "stack.toml"
    stack_file_path.parent.mkdir(parents=True, exist_ok=True)
    stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")
    return LoadedStack(stack_file_path=stack_file_path, stack_definition=stack_definition)


def _capture_workflow_calls() -> tuple[list[dict[str, object]], Callable[..., None]]:
    captured_calls: list[dict[str, object]] = []

    def run_workflow(**workflow_kwargs: object) -> None:
        captured_calls.append(workflow_kwargs)

    return captured_calls, run_workflow


class PlatformCommandContextTests(unittest.TestCase):
    def test_resolve_stack_file_path_raises_for_missing_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            with self.assertRaises(click.ClickException):
                command_context.resolve_stack_file_path(repo_root, Path("platform/stack.toml"))


class PlatformCommandsCoreTests(unittest.TestCase):
    def test_execute_validate_config_reports_ok(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")

            loaded_stack = LoadedStack(stack_file_path=stack_file_path, stack_definition=_sample_stack_definition())

            with patch("tools.platform.commands_core.click.echo") as echo_mock:
                commands_core.execute_validate_config(
                    stack_file=Path("platform/stack.toml"),
                    env_file=None,
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    load_environment_fn=lambda _repo_root, _env_file: (repo_root / ".env", {"REQUIRED_KEY": "1"}),
                )

            emitted_lines = [call.args[0] for call in echo_mock.call_args_list]
            self.assertIn("validation=ok", emitted_lines)

    def test_execute_info_emits_missing_required_keys(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")

            loaded_stack = LoadedStack(stack_file_path=stack_file_path, stack_definition=_sample_stack_definition())
            captured_payload: dict[str, object] = {}

            def emit_payload(payload_data: dict[str, object], *, json_output: bool) -> None:
                captured_payload["payload"] = payload_data
                captured_payload["json_output"] = json_output

            commands_core.execute_info(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                json_output=True,
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", {}),
                dokploy_status_payload_fn=lambda **_kwargs: {"state": "ok"},
                emit_payload_fn=emit_payload,
            )

            payload = captured_payload["payload"]
            assert isinstance(payload, dict)
            self.assertEqual(payload.get("missing_required_env_keys"), ["REQUIRED_KEY"])
            self.assertEqual(captured_payload["json_output"], True)


class PlatformCommandsWorkflowTests(unittest.TestCase):
    def test_prompt_choice_uses_questionary_in_tty_mode(self) -> None:
        class _FakePrompt:
            def __init__(self, answer: str) -> None:
                self._answer = answer

            def ask(self) -> str:
                return self._answer

        class _FakeQuestionary:
            @staticmethod
            def select(prompt_text: str, choices: list[str], default: str | None, use_shortcuts: bool) -> _FakePrompt:
                self.assertEqual(prompt_text, "Select context")
                self.assertEqual(choices, ["cm", "opw"])
                self.assertEqual(default, "cm")
                self.assertTrue(use_shortcuts)
                return _FakePrompt("opw")

        with (
            patch.object(commands_workflow, "questionary", _FakeQuestionary),
            patch("tools.platform.commands_workflow.sys.stdin.isatty", return_value=True),
            patch("tools.platform.commands_workflow.sys.stdout.isatty", return_value=True),
        ):
            selected_context_name = commands_workflow._prompt_choice(
                prompt_text="Select context",
                choices=("cm", "opw"),
                default_choice="cm",
            )

        self.assertEqual(selected_context_name, "opw")

    def test_prompt_choice_falls_back_to_click_prompt(self) -> None:
        with (
            patch.object(commands_workflow, "questionary", None),
            patch("tools.platform.commands_workflow.click.prompt", return_value="cm") as click_prompt_mock,
        ):
            selected_context_name = commands_workflow._prompt_choice(
                prompt_text="Select context",
                choices=("cm", "opw"),
            )

        self.assertEqual(selected_context_name, "cm")
        click_prompt_mock.assert_called_once()

    def test_execute_tui_command_prompts_and_runs_selected_workflow(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            captured_calls, run_workflow = _capture_workflow_calls()

            with (
                patch(
                    "tools.platform.commands_workflow.click.prompt",
                    side_effect=["cm", "status", "local"],
                ),
                patch("tools.platform.commands_workflow.click.echo"),
            ):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name=None,
                    instance_name=None,
                    workflow=None,
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda _context_definition: ["local", "testing"],
                    run_workflow_fn=run_workflow,
                )

            self.assertEqual(len(captured_calls), 1)
            self.assertEqual(captured_calls[0]["context_name"], "cm")
            self.assertEqual(captured_calls[0]["instance_name"], "local")
            self.assertEqual(captured_calls[0]["workflow"], "status")

    def test_execute_tui_command_with_context_wildcard_runs_all_contexts(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )
            captured_calls, run_workflow = _capture_workflow_calls()

            with patch("tools.platform.commands_workflow.click.echo"):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="all",
                    instance_name="local",
                    workflow="status",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=run_workflow,
                )

            self.assertEqual(len(captured_calls), 2)
            self.assertEqual(
                {(call["context_name"], call["instance_name"]) for call in captured_calls},
                {("cm", "local"), ("opw", "local")},
            )

    def test_execute_tui_command_with_context_list_runs_selected_contexts(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )
            captured_calls, run_workflow = _capture_workflow_calls()

            with patch("tools.platform.commands_workflow.click.echo"):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm,opw",
                    instance_name="local",
                    workflow="status",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=run_workflow,
                )

            self.assertEqual(len(captured_calls), 2)
            self.assertEqual(
                {(call["context_name"], call["instance_name"]) for call in captured_calls},
                {("cm", "local"), ("opw", "local")},
            )

    def test_execute_tui_command_context_wildcard_fails_when_instance_missing_in_any_context(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="all",
                    instance_name="testing",
                    workflow="status",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                )

            self.assertIn("Instance 'testing' is not available in contexts: opw", captured_error.exception.message)

    def test_execute_tui_command_with_instance_wildcard_runs_all_instances(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            captured_calls, run_workflow = _capture_workflow_calls()

            with patch("tools.platform.commands_workflow.click.echo"):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="all",
                    workflow="status",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=run_workflow,
                )

            self.assertEqual(len(captured_calls), 2)
            self.assertEqual(
                {(call["context_name"], call["instance_name"]) for call in captured_calls},
                {("cm", "local"), ("cm", "testing")},
            )

    def test_execute_tui_command_with_instance_list_runs_selected_instances(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            captured_calls, run_workflow = _capture_workflow_calls()

            with patch("tools.platform.commands_workflow.click.echo"):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="local,testing",
                    workflow="info",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=run_workflow,
                )

            self.assertEqual(len(captured_calls), 2)
            self.assertEqual(
                {(call["context_name"], call["instance_name"]) for call in captured_calls},
                {("cm", "local"), ("cm", "testing")},
            )

    def test_execute_tui_command_ship_requires_deploy_instance(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="local",
                    workflow="ship",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "ship"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                    run_ship_fn=lambda **_kwargs: None,
                    check_dirty_working_tree_fn=lambda: (),
                )

            self.assertIn("supports only deploy instances", captured_error.exception.message)

    def test_execute_tui_command_ship_clean_tree_runs_without_allow_dirty(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            captured_calls: list[dict[str, object]] = []

            def run_ship(**ship_kwargs: object) -> None:
                captured_calls.append(ship_kwargs)

            commands_workflow.execute_tui_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                workflow="ship",
                env_file=None,
                dry_run=False,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                json_output=False,
                allow_prod_data_workflow=False,
                platform_tui_workflows=("status", "info", "ship"),
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                run_workflow_fn=lambda **_kwargs: None,
                run_ship_fn=run_ship,
                check_dirty_working_tree_fn=lambda: (),
            )

            self.assertEqual(len(captured_calls), 1)
            self.assertEqual(captured_calls[0]["context_name"], "cm")
            self.assertEqual(captured_calls[0]["instance_name"], "testing")
            self.assertEqual(captured_calls[0]["allow_dirty"], False)

    def test_execute_tui_command_ship_dirty_tree_requires_confirmation(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            captured_calls: list[dict[str, object]] = []

            def run_ship(**ship_kwargs: object) -> None:
                captured_calls.append(ship_kwargs)

            with (
                patch.object(commands_workflow, "questionary", None),
                patch("tools.platform.commands_workflow.sys.stdin.isatty", return_value=True),
                patch("tools.platform.commands_workflow.sys.stdout.isatty", return_value=True),
                patch("tools.platform.commands_workflow.click.confirm", return_value=True),
            ):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="testing",
                    workflow="ship",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "ship"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                    run_ship_fn=run_ship,
                    check_dirty_working_tree_fn=lambda: (" M platform/dokploy.toml",),
                )

            self.assertEqual(len(captured_calls), 1)
            self.assertEqual(captured_calls[0]["allow_dirty"], True)

    def test_execute_tui_command_ship_dirty_tree_non_interactive_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with (
                patch.object(commands_workflow, "questionary", None),
                patch("tools.platform.commands_workflow.sys.stdin.isatty", return_value=False),
                patch("tools.platform.commands_workflow.sys.stdout.isatty", return_value=False),
                self.assertRaises(click.ClickException) as captured_error,
            ):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="testing",
                    workflow="ship",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "ship"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                    run_ship_fn=lambda **_kwargs: None,
                    check_dirty_working_tree_fn=lambda: ("M platform/dokploy.toml",),
                )

            self.assertIn("platform ship --allow-dirty", captured_error.exception.message)

    def test_execute_tui_command_ship_rejects_json_output(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="testing",
                    workflow="ship",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=True,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "ship"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                    run_ship_fn=lambda **_kwargs: None,
                    check_dirty_working_tree_fn=lambda: (),
                )

            self.assertIn("JSON output is not supported", captured_error.exception.message)

    def test_execute_tui_command_rejects_mixed_wildcard_and_named_selector_values(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="all,cm",
                    instance_name="local",
                    workflow="status",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                )

            self.assertIn("cannot mix wildcard", captured_error.exception.message)

    def test_execute_tui_command_rejects_unsafe_workflow_for_explicit_context_fanout(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm,opw",
                    instance_name="local",
                    workflow="up",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                )

            self.assertIn("Fan-out context runs are limited", captured_error.exception.message)

    def test_execute_tui_command_rejects_unsafe_workflow_for_explicit_instance_fanout(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException) as captured_error:
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="local,testing",
                    workflow="up",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "info", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                )

            self.assertIn("Fan-out runs are limited", captured_error.exception.message)

    def test_execute_tui_command_rejects_unsafe_workflow_with_wildcard(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException):
                commands_workflow.execute_tui_command(
                    stack_file=Path("platform/stack.toml"),
                    context_name="all",
                    instance_name="all",
                    workflow="up",
                    env_file=None,
                    dry_run=False,
                    no_cache=False,
                    no_sanitize=False,
                    force=False,
                    reset_versions=False,
                    json_output=False,
                    allow_prod_data_workflow=False,
                    platform_tui_workflows=("status", "up"),
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    ordered_instance_names_fn=lambda context_definition: list(context_definition.instances),
                    run_workflow_fn=lambda **_kwargs: None,
                )

    def test_execute_init_command_enforces_guard(self) -> None:
        captured_calls: list[dict[str, object]] = []

        def guard(**kwargs: object) -> None:
            captured_calls.append({"guard": kwargs})

        def runner(**kwargs: object) -> None:
            captured_calls.append({"run": kwargs})

        commands_workflow.execute_init_command(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="local",
            env_file=None,
            dry_run=False,
            allow_prod_data_workflow=False,
            assert_prod_data_workflow_allowed_fn=guard,
            run_init_workflow_fn=runner,
        )

        self.assertEqual(len(captured_calls), 2)
        self.assertIn("guard", captured_calls[0])
        self.assertIn("run", captured_calls[1])

    def test_execute_restore_command_allows_remote_instance(self) -> None:
        captured_kwargs: dict[str, object] = {}

        def runner(**kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        commands_workflow.execute_restore_command(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="testing",
            env_file=None,
            dry_run=True,
            no_sanitize=False,
            allow_prod_data_workflow=False,
            run_workflow_fn=runner,
        )

        self.assertEqual(captured_kwargs["workflow"], "restore")
        self.assertEqual(captured_kwargs["instance_name"], "testing")

    def test_execute_bootstrap_command_allows_remote_instance(self) -> None:
        captured_kwargs: dict[str, object] = {}

        def runner(**kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        commands_workflow.execute_bootstrap_command(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="testing",
            env_file=None,
            dry_run=True,
            no_sanitize=False,
            allow_prod_data_workflow=False,
            run_workflow_fn=runner,
        )

        self.assertEqual(captured_kwargs["workflow"], "bootstrap")
        self.assertEqual(captured_kwargs["instance_name"], "testing")

    def test_execute_run_workflow_command_rejects_remote_local_only_workflow(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_run_workflow_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                env_file=None,
                workflow="init",
                dry_run=True,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("requires --instance local", captured_error.exception.message)

    def test_run_workflow_for_targets_marks_remote_local_runtime_target_failed(self) -> None:
        emitted_lines: list[str] = []

        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow._run_workflow_for_targets(
                stack_file=Path("platform/stack.toml"),
                env_file=None,
                workflow="up",
                dry_run=False,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                allow_prod_data_workflow=False,
                target_pairs=(("cm", "testing"),),
                run_workflow_fn=lambda **_kwargs: None,
                echo_fn=emitted_lines.append,
                json_output=False,
            )

        self.assertIn("1 target run(s) failed", captured_error.exception.message)
        self.assertTrue(any("requires --instance local" in line for line in emitted_lines))

    def test_run_workflow_for_targets_emits_summary(self) -> None:
        emitted_lines: list[str] = []
        captured_calls: list[tuple[str, str]] = []

        def run_workflow(**kwargs: object) -> None:
            context_name = kwargs["context_name"]
            instance_name = kwargs["instance_name"]
            assert isinstance(context_name, str)
            assert isinstance(instance_name, str)
            captured_calls.append((context_name, instance_name))

        commands_workflow._run_workflow_for_targets(
            stack_file=Path("platform/stack.toml"),
            env_file=None,
            workflow="status",
            dry_run=False,
            no_cache=False,
            no_sanitize=False,
            force=False,
            reset_versions=False,
            allow_prod_data_workflow=False,
            target_pairs=(("cm", "local"), ("opw", "local")),
            run_workflow_fn=run_workflow,
            echo_fn=emitted_lines.append,
            json_output=False,
        )

        self.assertEqual(captured_calls, [("cm", "local"), ("opw", "local")])
        self.assertTrue(any(line == "tui_summary" for line in emitted_lines))
        self.assertTrue(any("Context" in line and "Instance" in line and "Status" in line for line in emitted_lines))
        self.assertTrue(any("cm" in line and "local" in line and "ok" in line for line in emitted_lines))

    def test_run_workflow_for_targets_raises_after_failed_runs(self) -> None:
        emitted_lines: list[str] = []
        captured_calls: list[tuple[str, str]] = []

        def run_workflow(**kwargs: object) -> None:
            context_name = kwargs["context_name"]
            instance_name = kwargs["instance_name"]
            assert isinstance(context_name, str)
            assert isinstance(instance_name, str)
            captured_calls.append((context_name, instance_name))
            if context_name == "opw":
                raise click.ClickException("remote status unavailable")

        with self.assertRaises(click.ClickException):
            commands_workflow._run_workflow_for_targets(
                stack_file=Path("platform/stack.toml"),
                env_file=None,
                workflow="status",
                dry_run=False,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                allow_prod_data_workflow=False,
                target_pairs=(("cm", "local"), ("opw", "local")),
                run_workflow_fn=run_workflow,
                echo_fn=emitted_lines.append,
                json_output=False,
            )

        self.assertEqual(captured_calls, [("cm", "local"), ("opw", "local")])
        self.assertTrue(any("failed" in line and "remote status unavailable" in line for line in emitted_lines))

    def test_run_workflow_for_targets_emits_json_summary_and_suppresses_noise(self) -> None:
        emitted_lines: list[str] = []

        def run_workflow(*, echo_fn: Callable[[str], None], **_workflow_kwargs: object) -> None:
            echo_fn("unstructured workflow output")

        commands_workflow._run_workflow_for_targets(
            stack_file=Path("platform/stack.toml"),
            env_file=None,
            workflow="status",
            dry_run=False,
            no_cache=False,
            no_sanitize=False,
            force=False,
            reset_versions=False,
            allow_prod_data_workflow=False,
            target_pairs=(("cm", "local"), ("opw", "local")),
            run_workflow_fn=run_workflow,
            echo_fn=emitted_lines.append,
            json_output=True,
        )

        self.assertEqual(len(emitted_lines), 1)
        summary_payload = json.loads(emitted_lines[0])
        self.assertEqual(summary_payload["total_runs"], 2)
        self.assertEqual(summary_payload["failed_runs"], 0)
        self.assertEqual(
            summary_payload["runs"],
            [
                {
                    "context": "cm",
                    "instance": "local",
                    "status": "ok",
                    "detail": "completed",
                },
                {
                    "context": "opw",
                    "instance": "local",
                    "status": "ok",
                    "detail": "completed",
                },
            ],
        )

    def test_run_workflow_for_targets_json_summary_includes_failures(self) -> None:
        emitted_lines: list[str] = []

        def run_workflow(*, context_name: str, echo_fn: Callable[[str], None], **_kwargs: object) -> None:
            if context_name == "opw":
                raise click.ClickException("remote status unavailable")
            echo_fn("unstructured workflow output")

        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow._run_workflow_for_targets(
                stack_file=Path("platform/stack.toml"),
                env_file=None,
                workflow="status",
                dry_run=False,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                allow_prod_data_workflow=False,
                target_pairs=(("cm", "local"), ("opw", "local")),
                run_workflow_fn=run_workflow,
                echo_fn=emitted_lines.append,
                json_output=True,
            )

        self.assertIn("1 target run(s) failed", captured_error.exception.message)
        self.assertEqual(len(emitted_lines), 1)
        summary_payload = json.loads(emitted_lines[0])
        self.assertEqual(summary_payload["total_runs"], 2)
        self.assertEqual(summary_payload["failed_runs"], 1)
        self.assertEqual(summary_payload["runs"][1]["status"], "failed")
        self.assertEqual(summary_payload["runs"][1]["detail"], "remote status unavailable")

    def test_run_workflow_for_targets_json_summary_schema_is_stable(self) -> None:
        emitted_lines: list[str] = []

        commands_workflow._run_workflow_for_targets(
            stack_file=Path("platform/stack.toml"),
            env_file=None,
            workflow="status",
            dry_run=False,
            no_cache=False,
            no_sanitize=False,
            force=False,
            reset_versions=False,
            allow_prod_data_workflow=False,
            target_pairs=(("cm", "local"),),
            run_workflow_fn=lambda **_kwargs: None,
            echo_fn=emitted_lines.append,
            json_output=True,
        )

        self.assertEqual(len(emitted_lines), 1)
        summary_payload = json.loads(emitted_lines[0])
        self.assertEqual(set(summary_payload), {"total_runs", "failed_runs", "runs"})
        self.assertIsInstance(summary_payload["runs"], list)
        self.assertEqual(len(summary_payload["runs"]), 1)

        run_payload = summary_payload["runs"][0]
        assert isinstance(run_payload, dict)
        self.assertEqual(set(run_payload), {"context", "instance", "status", "detail"})


class PlatformCommandsSelectionTests(unittest.TestCase):
    def test_execute_select_dry_run_emits_payload(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")

            loaded_stack = LoadedStack(stack_file_path=stack_file_path, stack_definition=_sample_stack_definition())
            loaded_environment = LoadedEnvironment(
                env_file_path=repo_root / ".env",
                merged_values={"REQUIRED_KEY": "1"},
                source_by_key={"REQUIRED_KEY": ".env"},
                collisions=(EnvironmentCollision(key="REQUIRED_KEY", previous_layer="root", incoming_layer="context"),),
            )
            captured_payload: dict[str, object] = {}

            def emit_payload(payload_data: dict[str, object], *, json_output: bool) -> None:
                captured_payload["payload"] = payload_data
                captured_payload["json_output"] = json_output

            commands_selection.execute_select(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=True,
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_with_details_fn=lambda _repo_root, _env_file, **_kwargs: loaded_environment,
                build_runtime_env_values_fn=lambda *_args, **_kwargs: {"REQUIRED_KEY": "1", "NEW_KEY": "value"},
                parse_env_file_fn=lambda _path: {"REQUIRED_KEY": "1"},
                runtime_env_diff_fn=lambda _current, _new: {"added": ["NEW_KEY"]},
                emit_payload_fn=emit_payload,
                write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: Path("unused"),
                write_runtime_env_file_fn=lambda *_args, **_kwargs: Path("unused"),
                echo_fn=lambda _line: None,
            )

            payload = captured_payload["payload"]
            assert isinstance(payload, dict)
            self.assertTrue(payload.get("dry_run"))
            self.assertEqual(payload.get("runtime_env_diff"), {"added": ["NEW_KEY"]})

    def test_execute_select_rejects_non_local_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_selection.execute_select(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                env_file=None,
                dry_run=True,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_stack_fn=lambda _path: (_ for _ in ()).throw(AssertionError("should not run")),
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_with_details_fn=lambda _repo_root, _env_file, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("should not run")
                ),
                build_runtime_env_values_fn=lambda *_args, **_kwargs: {},
                parse_env_file_fn=lambda _path: {},
                runtime_env_diff_fn=lambda _current, _new: {},
                emit_payload_fn=lambda _payload, **_kwargs: None,
                write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: Path("unused"),
                write_runtime_env_file_fn=lambda *_args, **_kwargs: Path("unused"),
                echo_fn=lambda _line: None,
            )

        self.assertIn("requires --instance local", captured_error.exception.message)

    def test_execute_select_writes_pycharm_config_path(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root_path = Path(temporary_directory_name)
            stack_file_path = repo_root_path / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")

            loaded_stack = LoadedStack(stack_file_path=stack_file_path, stack_definition=_sample_stack_definition())
            loaded_environment = LoadedEnvironment(
                env_file_path=repo_root_path / ".env",
                merged_values={"REQUIRED_KEY": "1"},
                source_by_key={"REQUIRED_KEY": ".env"},
                collisions=(),
            )
            emitted_lines: list[str] = []
            pycharm_conf_calls: list[dict[str, str]] = []

            def write_pycharm_odoo_conf(
                *,
                repo_root: Path,
                runtime_selection: RuntimeSelection,
                stack_definition: StackDefinition,
                source_environment: dict[str, str],
            ) -> Path:
                self.assertEqual(repo_root, repo_root_path)
                self.assertEqual(runtime_selection.context_name, "cm")
                self.assertEqual(stack_definition.schema_version, 1)
                pycharm_conf_calls.append(source_environment)
                return repo_root / ".platform" / "ide" / "cm.local.odoo.conf"

            commands_selection.execute_select(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=False,
                discover_repo_root_fn=lambda _path: repo_root_path,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_with_details_fn=lambda _repo_root, _env_file, **_kwargs: loaded_environment,
                build_runtime_env_values_fn=lambda *_args, **_kwargs: {
                    "DOCKER_IMAGE": "odoo-ai",
                    "DOCKER_IMAGE_TAG": "latest",
                },
                parse_env_file_fn=lambda _path: {},
                runtime_env_diff_fn=lambda _current, _new: {},
                emit_payload_fn=lambda _payload, **_kwargs: None,
                write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: Path("unused"),
                write_runtime_env_file_fn=lambda *_args, **_kwargs: Path("unused"),
                echo_fn=emitted_lines.append,
                write_pycharm_odoo_conf_fn=write_pycharm_odoo_conf,
            )

            self.assertEqual(len(pycharm_conf_calls), 1)
            self.assertIn("pycharm_odoo_conf_file=", "\n".join(emitted_lines))

    def test_execute_inspect_reports_pycharm_config_path(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")
            loaded_stack = LoadedStack(stack_file_path=stack_file_path, stack_definition=_sample_stack_definition())

            with patch("tools.platform.commands_selection.click.echo") as echo_mock:
                commands_selection.execute_inspect(
                    stack_file=Path("platform/stack.toml"),
                    context_name="cm",
                    instance_name="local",
                    env_file=None,
                    json_output=False,
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                        repo_root / ".env",
                        {"ODOO_DB_USER": "odoo", "ODOO_DB_PASSWORD": "pw"},
                    ),
                    write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: repo_root / ".platform" / "state" / "cm-local" / "platform.odoo.conf",
                    write_pycharm_odoo_conf_fn=lambda **_kwargs: repo_root / ".platform" / "ide" / "cm.local.odoo.conf",
                )

            emitted_lines = [call.args[0] for call in echo_mock.call_args_list]
            self.assertIn(f"pycharm_odoo_conf_host={repo_root / '.platform' / 'ide' / 'cm.local.odoo.conf'}", emitted_lines)


class PlatformCommandsLifecycleTests(unittest.TestCase):
    def test_execute_down_requires_runtime_env_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            with self.assertRaises(click.ClickException):
                commands_lifecycle.execute_down(
                    context_name="cm",
                    instance_name="local",
                    volumes=False,
                    discover_repo_root_fn=lambda _path: repo_root,
                    compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
                    run_command_fn=lambda _command: None,
                )

    def test_execute_up_rejects_non_local_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_lifecycle.execute_up(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                env_file=None,
                build_images=True,
                no_cache=False,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_stack_fn=lambda _path: (_ for _ in ()).throw(AssertionError("should not run")),
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: Path("unused"),
                write_runtime_env_file_fn=lambda *_args, **_kwargs: Path("unused"),
                ensure_registry_auth_for_base_images_fn=lambda _environment_values: None,
                compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
                run_command_fn=lambda _command: None,
            )

        self.assertIn("requires --instance local", captured_error.exception.message)


class PlatformCommandsDokployTests(unittest.TestCase):
    def test_resolve_dokploy_compose_remote_config_reads_app_name_from_compose_payload(self) -> None:
        with patch.object(platform_dokploy, "dokploy_request", return_value={"composeId": "compose-id-2", "appName": "odoo-cm-dev-b"}):
            remote_stack_path, compose_project = platform_dokploy.resolve_dokploy_compose_remote_config(
                host="https://dokploy.example",
                token="token",
                compose_id="compose-id-2",
                compose_name="cm-dev",
            )

        self.assertEqual(remote_stack_path, Path("/etc/dokploy/applications/odoo-cm-dev-b"))
        self.assertEqual(compose_project, "odoo-cm-dev-b")

    def test_resolve_dokploy_compose_remote_config_requires_app_name(self) -> None:
        with patch.object(platform_dokploy, "dokploy_request", return_value={"composeId": "compose-id-2"}):
            with self.assertRaises(click.ClickException) as raised_error:
                platform_dokploy.resolve_dokploy_compose_remote_config(
                    host="https://dokploy.example",
                    token="token",
                    compose_id="compose-id-2",
                    compose_name="cm-dev",
                )

        self.assertIn("has no appName", str(raised_error.exception))

    def test_execute_reconcile_fails_when_target_missing_from_stack(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(
                    DokployTargetDefinition(context="cm", instance="prod", target_id="compose-id",
                                            target_name="cm-prod"),
                ),
            )

            with self.assertRaises(click.ClickException) as captured_error:
                commands_dokploy.execute_reconcile(
                    stack_file=Path("platform/stack.toml"),
                    source_file=Path("platform/dokploy.toml"),
                    env_file=None,
                    context_filter=None,
                    instance_filter=None,
                    apply=False,
                    prune_env=False,
                    json_output=False,
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_stack_fn=lambda _path: loaded_stack,
                    resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: _source_file
                    if _source_file is not None
                    else Path("platform/dokploy.toml"),
                    load_dokploy_source_of_truth_fn=lambda _source_file_path: source_of_truth,
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                    read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                    target_matches_filters_fn=lambda *_args, **_kwargs: True,
                    fetch_dokploy_target_payload_fn=lambda **_kwargs: {},
                    normalize_domains_fn=lambda _raw_domains: [],
                    dokploy_request_fn=lambda **_kwargs: {},
                    update_dokploy_target_env_fn=lambda **_kwargs: None,
                    parse_dokploy_env_text_fn=lambda _text: {},
                    serialize_dokploy_env_text_fn=lambda _env_map: "",
                    emit_payload_fn=lambda _payload, **_kwargs: None,
                )

            self.assertIn("is not defined in", captured_error.exception.message)

    def test_execute_reconcile_loads_environment_per_target_scope(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(
                    DokployTargetDefinition(context="cm", instance="local", target_id="cm-local-compose-id",
                                            target_name="cm-local"),
                    DokployTargetDefinition(context="opw", instance="local", target_id="opw-local-compose-id",
                                            target_name="opw-local"),
                ),
            )

            resolved_scopes: list[tuple[str | None, str | None]] = []
            resolved_collision_modes: list[str | None] = []
            captured_payloads: list[dict[str, object]] = []

            def load_environment(
                _repo_root: Path,
                _env_file: Path | None,
                **kwargs: object,
            ) -> tuple[Path, dict[str, str]]:
                context_name = kwargs.get("context_name")
                instance_name = kwargs.get("instance_name")
                collision_mode = kwargs.get("collision_mode")
                context_value = str(context_name) if context_name is not None else None
                instance_value = str(instance_name) if instance_name is not None else None
                resolved_scopes.append((context_value, instance_value))
                resolved_collision_modes.append(str(collision_mode) if collision_mode is not None else None)
                return Path("/tmp/.env"), {
                    "DOKPLOY_HOST": "https://dokploy.example",
                    "DOKPLOY_TOKEN": "token",
                }

            commands_dokploy.execute_reconcile(
                stack_file=Path("platform/stack.toml"),
                source_file=Path("platform/dokploy.toml"),
                env_file=None,
                context_filter=None,
                instance_filter=None,
                apply=False,
                prune_env=False,
                json_output=False,
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: _source_file
                if _source_file is not None
                else Path("platform/dokploy.toml"),
                load_dokploy_source_of_truth_fn=lambda _source_file_path: source_of_truth,
                load_environment_fn=load_environment,
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                target_matches_filters_fn=lambda *_args, **_kwargs: True,
                fetch_dokploy_target_payload_fn=lambda **_kwargs: {"name": "compose-name", "domains": [], "env": ""},
                normalize_domains_fn=lambda _raw_domains: [],
                dokploy_request_fn=lambda **_kwargs: {},
                update_dokploy_target_env_fn=lambda **_kwargs: None,
                parse_dokploy_env_text_fn=lambda _text: {},
                serialize_dokploy_env_text_fn=lambda _env_map: "",
                emit_payload_fn=lambda payload, **_kwargs: captured_payloads.append(payload),
            )

            self.assertEqual(resolved_scopes, [("cm", "local"), ("opw", "local")])
            self.assertEqual(resolved_collision_modes, ["error", "error"])
            self.assertEqual(len(captured_payloads), 1)
            self.assertEqual(captured_payloads[0].get("matched_targets"), 2)

    def test_execute_reconcile_prunes_managed_env_keys_when_enabled(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(
                repo_root,
                stack_definition=_sample_multi_context_stack_definition(),
            )
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(
                    DokployTargetDefinition(context="cm", instance="local", target_id="cm-local-compose-id",
                                            target_name="cm-local", env={
                            "ENV_OVERRIDE_KEEP": "desired",
                            "ODOO_WEB_COMMAND": "python3 /volumes/scripts/run_odoo_startup.py",
                        }),
                ),
            )

            target_updates: list[dict[str, object]] = []
            captured_payloads: list[dict[str, object]] = []

            def update_target_env(**kwargs: object) -> None:
                target_updates.append(dict(kwargs))

            commands_dokploy.execute_reconcile(
                stack_file=Path("platform/stack.toml"),
                source_file=Path("platform/dokploy.toml"),
                env_file=None,
                context_filter=None,
                instance_filter=None,
                apply=True,
                prune_env=True,
                json_output=False,
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: _source_file
                if _source_file is not None
                else Path("platform/dokploy.toml"),
                load_dokploy_source_of_truth_fn=lambda _source_file_path: source_of_truth,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                    Path("/tmp/.env"),
                    {"DOKPLOY_HOST": "https://dokploy.example", "DOKPLOY_TOKEN": "token"},
                ),
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                target_matches_filters_fn=lambda *_args, **_kwargs: True,
                fetch_dokploy_target_payload_fn=lambda **_kwargs: {
                    "name": "compose-name",
                    "domains": [],
                    "env": "ENV_OVERRIDE_KEEP=current\nENV_OVERRIDE_REMOVE=1\nUNMANAGED_KEY=preserve\nODOO_WEB_COMMAND=old",
                },
                normalize_domains_fn=lambda _raw_domains: [],
                dokploy_request_fn=lambda **_kwargs: {},
                update_dokploy_target_env_fn=update_target_env,
                parse_dokploy_env_text_fn=lambda _text: {
                    "ENV_OVERRIDE_KEEP": "current",
                    "ENV_OVERRIDE_REMOVE": "1",
                    "UNMANAGED_KEY": "preserve",
                    "ODOO_WEB_COMMAND": "old",
                },
                serialize_dokploy_env_text_fn=lambda env_map: "\n".join(
                    f"{env_key}={env_map[env_key]}" for env_key in sorted(env_map)
                ),
                emit_payload_fn=lambda payload, **_kwargs: captured_payloads.append(payload),
            )

            self.assertEqual(len(target_updates), 1)
            rendered_env_text = str(target_updates[0].get("env_text"))
            self.assertIn("ENV_OVERRIDE_KEEP=desired", rendered_env_text)
            self.assertIn("ODOO_WEB_COMMAND=python3 /volumes/scripts/run_odoo_startup.py", rendered_env_text)
            self.assertIn("UNMANAGED_KEY=preserve", rendered_env_text)
            self.assertNotIn("ENV_OVERRIDE_REMOVE=1", rendered_env_text)

            target_entries = captured_payloads[0].get("targets")
            self.assertIsInstance(target_entries, list)
            assert isinstance(target_entries, list)
            target_payload = target_entries[0]
            self.assertIsInstance(target_payload, dict)
            self.assertEqual(target_payload.get("env_needs_update_keys"), ["ENV_OVERRIDE_KEEP", "ODOO_WEB_COMMAND"])
            self.assertEqual(target_payload.get("env_pruned_keys"), ["ENV_OVERRIDE_REMOVE"])
            self.assertTrue(bool(target_payload.get("env_updated")))

    def test_execute_env_unset_requires_key_or_prefix(self) -> None:
        with self.assertRaises(click.ClickException):
            commands_dokploy.execute_env_unset(
                context_name="cm",
                instance_name="testing",
                env_file=None,
                target_type="compose",
                keys=(),
                prefixes=(),
                dry_run=True,
                json_output=False,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                resolve_dokploy_runtime_fn=lambda **_kwargs: ("", "", "", "", "", {}),
                fetch_dokploy_target_payload_fn=lambda **_kwargs: {},
                parse_dokploy_env_text_fn=lambda _text: {},
                update_dokploy_target_env_fn=lambda **_kwargs: None,
                serialize_dokploy_env_text_fn=lambda _env_map: "",
                emit_payload_fn=lambda _payload, **_kwargs: None,
            )

    def test_execute_env_set_updates_only_changed_keys(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            target_updates: list[dict[str, object]] = []
            captured_payloads: list[dict[str, object]] = []

            def parse_assignment(assignment: str) -> tuple[str, str]:
                key, value = assignment.split("=", 1)
                return key, value

            def update_target_env(**kwargs: object) -> None:
                target_updates.append(kwargs)

            def emit_payload(payload_data: dict[str, object], **_kwargs: object) -> None:
                captured_payloads.append(payload_data)

            commands_dokploy.execute_env_set(
                context_name="cm",
                instance_name="testing",
                env_file=None,
                target_type="compose",
                assignments=("A=1", "B=2"),
                dry_run=False,
                json_output=False,
                parse_env_assignment_fn=parse_assignment,
                discover_repo_root_fn=lambda _path: repo_root,
                resolve_dokploy_runtime_fn=lambda **_kwargs: (
                    "https://dokploy.example",
                    "token",
                    "compose",
                    "compose-id",
                    "compose-name",
                    {},
                ),
                fetch_dokploy_target_payload_fn=lambda **_kwargs: {"env": "A=0\nB=2"},
                parse_dokploy_env_text_fn=lambda _text: {"A": "0", "B": "2"},
                update_dokploy_target_env_fn=update_target_env,
                serialize_dokploy_env_text_fn=lambda env_map: "\n".join(f"{key}={value}" for key, value in sorted(env_map.items())),
                emit_payload_fn=emit_payload,
            )

            self.assertEqual(len(target_updates), 1)
            self.assertEqual(captured_payloads[0]["changed_keys"], ["A"])
            self.assertEqual(captured_payloads[0]["unchanged_keys"], ["B"])

    def test_execute_inventory_writes_summary_and_snapshots(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            captured_payloads: list[dict[str, object]] = []

            project_payload: JsonObject = {
                "projects": [
                    {
                        "name": "odoo-ai",
                        "projectId": "project-1",
                        "environments": [
                            {
                                "name": "production",
                                "environmentId": "environment-1",
                                "compose": [{"composeId": "compose-1", "name": "cm-dev"}],
                                "applications": [{"applicationId": "application-1", "name": "ops-dashboard"}],
                            }
                        ],
                    }
                ]
            }
            server_payload: JsonObject = {
                "data": [
                    {
                        "serverId": "server-1",
                        "name": "docker-cm-dev",
                        "serverType": "deploy",
                        "serverStatus": "active",
                        "ipAddress": "10.0.0.5",
                        "username": "root",
                        "port": 22,
                        "description": "CM dev host",
                    }
                ]
            }
            compose_target_payload: JsonObject = {
                "name": "cm-dev",
                "appName": "odoo-cm-dev",
                "serverId": "server-1",
                "server": {"name": "docker-cm-dev", "ipAddress": "10.0.0.5"},
                "domains": [{"host": "cm-dev.shinycomputers.com"}],
                "customGitBranch": "cm-dev",
                "customGitUrl": "git@github.com:cbusillo/odoo-ai.git",
                "composePath": "./docker-compose.yml",
                "sourceType": "git",
                "autoDeploy": True,
                "composeStatus": "done",
            }

            def dokploy_request(**kwargs: object) -> JsonValue:
                path = kwargs.get("path")
                if path == "/api/project.all":
                    return project_payload
                if path == "/api/server.all":
                    return server_payload
                raise AssertionError(f"Unexpected Dokploy path: {path}")

            def fetch_target_payload(**kwargs: object) -> JsonObject:
                self.assertEqual(kwargs.get("target_type"), "compose")
                self.assertEqual(kwargs.get("target_id"), "compose-1")
                return dict(compose_target_payload)

            def emit_payload(payload_data: dict[str, object], **_kwargs: object) -> None:
                captured_payloads.append(payload_data)

            commands_dokploy.execute_inventory(
                env_file=None,
                output_file=Path("tmp/dokploy-inventory.json"),
                snapshot_dir=Path("tmp/dokploy-snapshots"),
                json_output=False,
                discover_repo_root_fn=lambda _path: repo_root,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                    repo_root / ".env",
                    {"DOKPLOY_HOST": "https://dokploy.example", "DOKPLOY_TOKEN": "token"},
                ),
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                dokploy_request_fn=dokploy_request,
                fetch_dokploy_target_payload_fn=fetch_target_payload,
                emit_payload_fn=emit_payload,
            )

            self.assertEqual(len(captured_payloads), 1)
            payload = captured_payloads[0]
            self.assertEqual(payload.get("project_count"), 1)
            self.assertEqual(payload.get("compose_target_count"), 1)
            self.assertEqual(payload.get("application_target_count"), 1)
            self.assertEqual(payload.get("server_count"), 1)

            compose_targets = payload.get("compose_targets")
            self.assertIsInstance(compose_targets, list)
            assert isinstance(compose_targets, list)
            self.assertEqual(compose_targets[0]["target_name"], "cm-dev")
            self.assertEqual(compose_targets[0]["domains"], ["cm-dev.shinycomputers.com"])
            self.assertEqual(compose_targets[0]["server_name"], "docker-cm-dev")

            output_file = repo_root / "tmp" / "dokploy-inventory.json"
            snapshot_file = repo_root / "tmp" / "dokploy-snapshots" / "compose" / "cm-dev--compose-1.json"
            self.assertTrue(output_file.exists())
            self.assertTrue(snapshot_file.exists())

            rendered_output = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(rendered_output["compose_target_count"], 1)
            self.assertEqual(json.loads(snapshot_file.read_text(encoding="utf-8"))["appName"], "odoo-cm-dev")

    def test_execute_inventory_snapshot_names_remain_unique_for_duplicate_target_names(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            project_payload: JsonObject = {
                "projects": [
                    {
                        "name": "odoo-ai",
                        "projectId": "project-1",
                        "environments": [
                            {
                                "name": "production",
                                "environmentId": "environment-1",
                                "compose": [
                                    {"composeId": "compose-1", "name": "cm-dev"},
                                    {"composeId": "compose-2", "name": "cm-dev"},
                                ],
                                "applications": [],
                            }
                        ],
                    }
                ]
            }
            server_payload: JsonObject = {"data": []}

            def dokploy_request(**kwargs: object) -> JsonValue:
                path = kwargs.get("path")
                if path == "/api/project.all":
                    return project_payload
                if path == "/api/server.all":
                    return server_payload
                raise AssertionError(f"Unexpected Dokploy path: {path}")

            def fetch_target_payload(**kwargs: object) -> JsonObject:
                target_id = str(kwargs.get("target_id"))
                return {
                    "name": "cm-dev",
                    "appName": f"odoo-{target_id}",
                    "serverId": None,
                    "domains": [],
                    "customGitBranch": "cm-dev",
                    "customGitUrl": "git@github.com:cbusillo/odoo-ai.git",
                    "composePath": "./docker-compose.yml",
                    "sourceType": "git",
                    "autoDeploy": True,
                    "composeStatus": "done",
                }

            commands_dokploy.execute_inventory(
                env_file=None,
                output_file=None,
                snapshot_dir=Path("tmp/dokploy-snapshots"),
                json_output=False,
                discover_repo_root_fn=lambda _path: repo_root,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                    repo_root / ".env",
                    {"DOKPLOY_HOST": "https://dokploy.example", "DOKPLOY_TOKEN": "token"},
                ),
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                dokploy_request_fn=dokploy_request,
                fetch_dokploy_target_payload_fn=fetch_target_payload,
                emit_payload_fn=lambda _payload, **_kwargs: None,
            )

            snapshot_dir = repo_root / "tmp" / "dokploy-snapshots" / "compose"
            self.assertTrue((snapshot_dir / "cm-dev--compose-1.json").exists())
            self.assertTrue((snapshot_dir / "cm-dev--compose-2.json").exists())

class PlatformCommandsReleaseTests(unittest.TestCase):
    @staticmethod
    def _target_definition(
        *,
        context_name: str = "cm",
        instance_name: str = "dev",
        target_type: Literal["compose", "application"] = "compose",
    ) -> DokployTargetDefinition:
        return DokployTargetDefinition(
            context=context_name,
            instance=instance_name,
            target_type=target_type,
            target_id=f"{target_type}-id",
            target_name=f"{context_name}-{instance_name}-{target_type}",
        )

    @staticmethod
    def _source_of_truth(target_definition: DokployTargetDefinition) -> DokploySourceOfTruth:
        return DokploySourceOfTruth(schema_version=1, targets=(target_definition,))

    def _assert_execute_ship_wait_uses_predeploy_deployment_key(
        self,
        *,
        target_type: Literal["compose", "application"],
    ) -> None:
        call_order: list[str] = []
        target_definition = self._target_definition(target_type=target_type)
        source_of_truth = self._source_of_truth(target_definition)
        emitted_lines: list[str] = []

        def latest_deployment(_host: str, _token: str, _target_id: str) -> JsonObject:
            call_order.append("latest_before")
            deployment: JsonObject = {"id": "before"}
            return deployment

        def dokploy_request(**_kwargs: object) -> JsonObject:
            call_order.append("deploy")
            response: JsonObject = {}
            return response

        def wait_for_deployment(**kwargs: object) -> str:
            call_order.append("wait")
            self.assertEqual(kwargs.get("before_key"), "before")
            return "deployment=after status=done"

        commands_release.execute_ship(
            context_name="cm",
            instance_name="dev",
            env_file=None,
            wait=True,
            timeout_override_seconds=None,
            verify_health=False,
            health_timeout_override_seconds=None,
            dry_run=False,
            no_cache=False,
            skip_gate=False,
            source_git_ref="main",
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-dev.example/web/health",),
            prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: target_type,
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=lambda **_kwargs: (
                target_type,
                f"{target_type}-id",
                f"{target_type}-name",
                None,
                None,
            ),
            apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
            dokploy_request_fn=dokploy_request,
            latest_deployment_for_compose_fn=latest_deployment if target_type == "compose" else lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda deployment: str(deployment.get("id", "")) if isinstance(deployment, dict) else "",
            wait_for_dokploy_compose_deployment_fn=wait_for_deployment if target_type == "compose" else lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: None,
            latest_deployment_for_application_fn=latest_deployment if target_type == "application" else lambda _host, _token, _application_id: None,
            wait_for_dokploy_deployment_fn=wait_for_deployment if target_type == "application" else lambda **_kwargs: "",
            echo_fn=emitted_lines.append,
        )

        self.assertEqual(call_order, ["latest_before", "deploy", "wait"])
        self.assertIn("deployment=after status=done", emitted_lines)

    def test_execute_ship_passes_source_of_truth_target_definition_to_target_resolution(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition(target_type="compose")
        source_of_truth = self._source_of_truth(target_definition)
        seen_target_definitions: list[DokployTargetDefinition | None] = []

        def resolve_target(**kwargs: object) -> tuple[str, str, str, click.ClickException | None, click.ClickException | None]:
            target_definition_value = kwargs.get("target_definition")
            if target_definition_value is not None:
                self.assertIsInstance(target_definition_value, DokployTargetDefinition)
            typed_target_definition = target_definition_value if isinstance(target_definition_value, DokployTargetDefinition) else None
            seen_target_definitions.append(typed_target_definition)
            return "compose", "compose-id", "compose-name", None, None

        commands_release.execute_ship(
            context_name="cm",
            instance_name="dev",
            env_file=None,
            wait=False,
            timeout_override_seconds=None,
            verify_health=False,
            health_timeout_override_seconds=None,
            dry_run=True,
            no_cache=False,
            skip_gate=False,
            source_git_ref="main",
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
            prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=resolve_target,
            apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
            dokploy_request_fn=lambda **_kwargs: {},
            latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: None,
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=emitted_lines.append,
        )

        self.assertEqual(seen_target_definitions, [target_definition])

    def test_execute_ship_loads_environment_with_error_collision_mode(self) -> None:
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)
        load_kwargs: dict[str, object] = {}

        def load_environment(_repo_root: Path, _env_file: Path | None, **kwargs: object) -> tuple[Path, dict[str, str]]:
            load_kwargs.update(kwargs)
            return Path("/tmp/.env"), {}

        commands_release.execute_ship(
            context_name="cm",
            instance_name="dev",
            env_file=None,
            wait=False,
            timeout_override_seconds=None,
            verify_health=False,
            health_timeout_override_seconds=None,
            dry_run=True,
            no_cache=False,
            skip_gate=False,
            source_git_ref="main",
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=load_environment,
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
            prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
            apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
            dokploy_request_fn=lambda **_kwargs: {},
            latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: None,
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=lambda _line: None,
        )

        self.assertEqual(load_kwargs.get("collision_mode"), "error")

    def test_execute_ship_rejects_dirty_tracked_working_tree_by_default(self) -> None:
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        with self.assertRaises(click.ClickException) as captured_error:
            commands_release.execute_ship(
                context_name="cm",
                instance_name="dev",
                env_file=None,
                wait=False,
                timeout_override_seconds=None,
                verify_health=False,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                skip_gate=True,
                source_git_ref="main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
                check_dirty_working_tree_fn=lambda: ("M platform/dokploy.toml",),
            )

        self.assertIn("--allow-dirty", captured_error.exception.message)
        self.assertIn("M platform/dokploy.toml", captured_error.exception.message)

    def test_execute_ship_dry_run_rejects_dirty_tracked_working_tree_by_default(self) -> None:
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        with self.assertRaises(click.ClickException) as captured_error:
            commands_release.execute_ship(
                context_name="cm",
                instance_name="dev",
                env_file=None,
                wait=False,
                timeout_override_seconds=None,
                verify_health=False,
                health_timeout_override_seconds=None,
                dry_run=True,
                no_cache=False,
                skip_gate=True,
                source_git_ref="main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
                check_dirty_working_tree_fn=lambda: ("M platform/dokploy.toml",),
            )

        self.assertIn("--allow-dirty", captured_error.exception.message)
        self.assertIn("M platform/dokploy.toml", captured_error.exception.message)

    def test_execute_ship_allows_dirty_tree_when_override_is_enabled(self) -> None:
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        commands_release.execute_ship(
            context_name="cm",
            instance_name="dev",
            env_file=None,
            wait=False,
            timeout_override_seconds=None,
            verify_health=False,
            health_timeout_override_seconds=None,
            dry_run=False,
            no_cache=False,
            skip_gate=True,
            allow_dirty=True,
            source_git_ref="main",
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
            prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
            apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
            dokploy_request_fn=lambda **_kwargs: {},
            latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: None,
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=lambda _line: None,
            check_dirty_working_tree_fn=lambda: ("M platform/dokploy.toml",),
        )

    def test_run_required_gates_warns_when_skip_gate_bypasses_required_policy(self) -> None:
        target_definition = self._target_definition(instance_name="testing")
        target_definition = target_definition.model_copy(update={"require_test_gate": True})
        emitted_lines: list[str] = []

        release_workflows.run_required_gates(
            context_name="cm",
            target_definition=target_definition,
            dry_run=False,
            skip_gate=True,
            validate_target_gate_policy_fn=lambda **_kwargs: None,
            run_code_gate_fn=lambda **_kwargs: None,
            run_production_backup_gate_fn=lambda **_kwargs: None,
            echo_fn=emitted_lines.append,
        )

        self.assertEqual(len(emitted_lines), 1)
        self.assertIn("warning: skip_gate=true", emitted_lines[0])
        self.assertIn("require_test_gate=true", emitted_lines[0])

    def test_execute_ship_requires_dokploy_source_of_truth(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_release.execute_ship(
                context_name="cm",
                instance_name="dev",
                env_file=None,
                wait=False,
                timeout_override_seconds=None,
                verify_health=False,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                skip_gate=False,
                source_git_ref="main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: None,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: None,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
            )

        self.assertIn("requires platform/dokploy.toml", captured_error.exception.message)

    def test_execute_ship_requires_target_definition_in_source_of_truth(self) -> None:
        source_of_truth = self._source_of_truth(
            self._target_definition(instance_name="testing")
        )

        with self.assertRaises(click.ClickException) as captured_error:
            commands_release.execute_ship(
                context_name="cm",
                instance_name="dev",
                env_file=None,
                wait=False,
                timeout_override_seconds=None,
                verify_health=False,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                skip_gate=False,
                source_git_ref="main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: None,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
            )

        self.assertIn("is missing from platform/dokploy.toml", captured_error.exception.message)

    def test_execute_ship_compose_wait_uses_predeploy_deployment_key(self) -> None:
        self._assert_execute_ship_wait_uses_predeploy_deployment_key(target_type="compose")

    def test_execute_ship_application_wait_uses_predeploy_deployment_key(self) -> None:
        self._assert_execute_ship_wait_uses_predeploy_deployment_key(target_type="application")

    def test_execute_ship_dry_run_reports_missing_dokploy_config(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        commands_release.execute_ship(
            context_name="cm",
            instance_name="testing",
            env_file=None,
            wait=True,
            timeout_override_seconds=None,
            verify_health=True,
            health_timeout_override_seconds=None,
            dry_run=True,
            no_cache=False,
            skip_gate=False,
            source_git_ref="main",
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-testing.example/web/health",),
            prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: (_ for _ in ()).throw(click.ClickException("missing dokploy config")),
            resolve_dokploy_target_fn=lambda **_kwargs: ("", "", "", None, None),
            apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
            dokploy_request_fn=lambda **_kwargs: {},
            latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: None,
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=emitted_lines.append,
        )

        self.assertIn("dry_run_note=missing dokploy config", emitted_lines)

    def test_execute_ship_verify_health_fails_when_no_urls_resolved(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        with self.assertRaises(click.ClickException):
            commands_release.execute_ship(
                context_name="cm",
                instance_name="testing",
                env_file=None,
                wait=True,
                timeout_override_seconds=None,
                verify_health=True,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                skip_gate=True,
                source_git_ref="main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                prepare_ship_branch_sync_fn=lambda _source_git_ref, _target_definition: None,
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                apply_ship_branch_sync_fn=lambda _ship_branch_sync_plan: None,
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "deployment=after status=done",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=emitted_lines.append,
            )

    def test_execute_rollback_dry_run_reports_missing_dokploy_config(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition(target_type="application", instance_name="testing")
        source_of_truth = self._source_of_truth(target_definition)

        commands_release.execute_rollback(
            context_name="cm",
            instance_name="testing",
            env_file=None,
            rollback_id="",
            list_only=False,
            wait=False,
            timeout_seconds=300,
            dry_run=True,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "application",
            read_dokploy_config_fn=lambda _environment_values: (_ for _ in ()).throw(click.ClickException("missing dokploy config")),
            dokploy_request_fn=lambda **_kwargs: {},
            extract_deployments_fn=lambda _payload: [],
            collect_rollback_ids_fn=lambda _deployments: [],
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=emitted_lines.append,
        )

        self.assertIn(f"app_name={target_definition.target_name}", emitted_lines)
        self.assertIn("dry_run_note=missing dokploy config", emitted_lines)

    def test_execute_rollback_prefers_source_of_truth_target_id(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition(target_type="application", instance_name="testing")
        source_of_truth = self._source_of_truth(target_definition)
        seen_application_ids: list[str] = []

        def dokploy_request(**kwargs: object) -> JsonObject:
            query = kwargs.get("query")
            if isinstance(query, dict) and query.get("applicationId"):
                seen_application_ids.append(str(query["applicationId"]))
            response: JsonObject = {"items": []}
            return response

        commands_release.execute_rollback(
            context_name="cm",
            instance_name="testing",
            env_file=None,
            rollback_id="rollback-1",
            list_only=True,
            wait=False,
            timeout_seconds=300,
            dry_run=False,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "application",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            dokploy_request_fn=dokploy_request,
            extract_deployments_fn=lambda _payload: [],
            collect_rollback_ids_fn=lambda _deployments: [],
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
            deployment_key_fn=lambda _deployment: "",
            wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
            echo_fn=emitted_lines.append,
        )

        self.assertEqual(seen_application_ids, [target_definition.target_id])
        self.assertIn(f"application_id={target_definition.target_id}", emitted_lines)


if __name__ == "__main__":
    unittest.main()
