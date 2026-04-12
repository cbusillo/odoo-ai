import json
import subprocess
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest.mock import Mock, patch

import click

from tools.platform import (
    command_context,
    commands_core,
    commands_dokploy,
    commands_release,
    commands_workflow,
    release_workflows,
)
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

    def test_execute_restore_command_retires_remote_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_restore_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                env_file=None,
                dry_run=True,
                no_sanitize=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("'platform restore' is retired in odoo-ai.", captured_error.exception.message)
        self.assertIn("platform runtime restore --manifest /path/to/workspace.toml --instance testing", captured_error.exception.message)

    def test_execute_restore_command_retires_local_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_restore_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=True,
                no_sanitize=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("'platform restore' is retired in odoo-ai.", captured_error.exception.message)
        self.assertIn("platform runtime restore --manifest /path/to/workspace.toml --instance local", captured_error.exception.message)

    def test_execute_bootstrap_command_retires_remote_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_bootstrap_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="testing",
                env_file=None,
                dry_run=True,
                no_sanitize=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("'platform bootstrap' is retired in odoo-ai.", captured_error.exception.message)
        self.assertIn(
            "platform runtime workflow --manifest /path/to/workspace.toml --workflow bootstrap --instance testing",
            captured_error.exception.message,
        )

    def test_execute_bootstrap_command_retires_local_instance(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_bootstrap_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=True,
                no_sanitize=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("'platform bootstrap' is retired in odoo-ai.", captured_error.exception.message)
        self.assertIn(
            "platform runtime workflow --manifest /path/to/workspace.toml --workflow bootstrap --instance local",
            captured_error.exception.message,
        )

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

    def test_execute_run_workflow_command_retires_local_restore(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            commands_workflow.execute_run_workflow_command(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                workflow="restore",
                dry_run=True,
                no_cache=False,
                no_sanitize=False,
                force=False,
                reset_versions=False,
                allow_prod_data_workflow=False,
                run_workflow_fn=lambda **_kwargs: None,
            )

        self.assertIn("'platform restore' is retired in odoo-ai.", captured_error.exception.message)

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


class PlatformCommandsDokployTests(unittest.TestCase):
    def test_execute_reconcile_fails_when_target_missing_from_stack(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(DokployTargetDefinition(context="cm", instance="prod", target_id="compose-id", target_name="cm-prod"),),
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
                    resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: (
                        _source_file if _source_file is not None else Path("platform/dokploy.toml")
                    ),
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
                    DokployTargetDefinition(context="cm", instance="local", target_id="cm-local-compose-id", target_name="cm-local"),
                    DokployTargetDefinition(
                        context="opw", instance="local", target_id="opw-local-compose-id", target_name="opw-local"
                    ),
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
                resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: (
                    _source_file if _source_file is not None else Path("platform/dokploy.toml")
                ),
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
                    DokployTargetDefinition(
                        context="cm",
                        instance="local",
                        target_id="cm-local-compose-id",
                        target_name="cm-local",
                        env={
                            "ENV_OVERRIDE_KEEP": "desired",
                            "ODOO_WEB_COMMAND": "python3 /volumes/scripts/run_odoo_startup.py",
                        },
                    ),
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
                resolve_dokploy_source_file_fn=lambda _repo_root, _source_file: (
                    _source_file if _source_file is not None else Path("platform/dokploy.toml")
                ),
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
        git_branch: str | None = None,
    ) -> DokployTargetDefinition:
        resolved_git_branch = git_branch
        if resolved_git_branch is None:
            resolved_git_branch = f"{context_name}-{instance_name}" if target_type == "compose" else ""
        return DokployTargetDefinition(
            context=context_name,
            instance=instance_name,
            target_type=target_type,
            target_id=f"{target_type}-id",
            target_name=f"{context_name}-{instance_name}-{target_type}",
            git_branch=resolved_git_branch,
        )

    @staticmethod
    def _source_of_truth(target_definition: DokployTargetDefinition) -> DokploySourceOfTruth:
        return DokploySourceOfTruth(schema_version=1, targets=(target_definition,))

    @staticmethod
    def _commit_file(
        *,
        repository_directory: Path,
        relative_path: str,
        content: str,
        message: str,
    ) -> str:
        file_path = repository_directory / relative_path
        file_path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", relative_path], cwd=repository_directory, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repository_directory, check=True, capture_output=True, text=True)
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_directory,
            check=True,
            capture_output=True,
            text=True,
        )
        return commit_result.stdout.strip()

    def test_apply_ship_branch_sync_uses_force_with_lease(self) -> None:
        ship_branch_sync_plan = commands_release.ShipBranchSyncPlan(
            source_git_ref="origin/main",
            source_commit="abc123",
            target_remote_name="origin",
            target_branch="cm-dev",
            remote_branch_commit_before="def456",
            branch_update_required=True,
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            return ""

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            commands_release._apply_ship_branch_sync(repo_root=Path("/tmp/repo"), ship_branch_sync_plan=ship_branch_sync_plan)

        self.assertEqual(
            captured_commands,
            [
                [
                    "git",
                    "push",
                    "origin",
                    "--force-with-lease=refs/heads/cm-dev:def456",
                    "abc123:refs/heads/cm-dev",
                ]
            ],
        )

    def test_run_command_capture_sanitizes_git_wrapper_environment(self) -> None:
        result = Mock(returncode=0, stdout="ok", stderr="")

        with patch.dict(
            "os.environ",
            {
                "PLATFORM_CONTEXT": "cm",
                "GIT_DIR": "/tmp/other.git",
                "GIT_WORK_TREE": "/tmp/worktree",
                "KEEP_ME": "1",
            },
            clear=True,
        ):
            with patch.object(commands_release.subprocess, "run", return_value=result) as run_command:
                output = commands_release._run_command_capture(["git", "status"], repo_root=Path("/tmp/repo"))

        self.assertEqual(output, "ok")
        self.assertEqual(run_command.call_count, 1)
        run_kwargs = run_command.call_args.kwargs
        execution_environment = run_kwargs["env"]
        self.assertNotIn("PLATFORM_CONTEXT", execution_environment)
        self.assertNotIn("GIT_DIR", execution_environment)
        self.assertNotIn("GIT_WORK_TREE", execution_environment)
        self.assertEqual(execution_environment.get("KEEP_ME"), "1")

    def test_run_ship_branch_sync_fetches_source_remote(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="upstream/main",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "origin\nupstream\n"
            if command == ["git", "fetch", "upstream", "--prune"]:
                return ""
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(
                commands_release,
                "_resolve_symbolic_full_git_reference",
                return_value="refs/remotes/upstream/main",
            ):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=False):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "fetch", "upstream", "--prune"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"],
                ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_run_ship_branch_sync_skips_fetch_for_local_branch_named_like_remote_ref(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="upstream/main",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "origin\nupstream\n"
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(
                commands_release,
                "_resolve_symbolic_full_git_reference",
                return_value="refs/heads/upstream/main",
            ):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=True):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"],
                ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_run_ship_branch_sync_refreshes_stale_remote_tracking_source_ref_even_when_local(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="upstream/main",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "origin\nupstream\n"
            if command == ["git", "fetch", "upstream", "--prune"]:
                return ""
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(
                commands_release,
                "_resolve_symbolic_full_git_reference",
                return_value="refs/remotes/upstream/main",
            ):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=True):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "fetch", "upstream", "--prune"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"],
                ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_resolve_git_remote_for_reference_ignores_local_branch_named_like_remote_ref(self) -> None:
        with patch.object(commands_release, "_resolve_symbolic_full_git_reference", return_value="refs/heads/upstream/main"):
            remote_name = commands_release._resolve_git_remote_for_reference(
                repo_root=Path("/tmp/repo"),
                git_reference="upstream/main",
                configured_remotes=("origin", "upstream"),
            )

        self.assertEqual(remote_name, "")

    def test_resolve_git_remote_for_reference_accepts_explicit_remote_tracking_ref(self) -> None:
        remote_name = commands_release._resolve_git_remote_for_reference(
            repo_root=Path("/tmp/repo"),
            git_reference="refs/remotes/upstream/main",
            configured_remotes=("origin", "upstream"),
        )

        self.assertEqual(remote_name, "upstream")

    def test_git_reference_is_remote_tracking_accepts_symbolic_remote_tracking_ref(self) -> None:
        with patch.object(
            commands_release,
            "_resolve_symbolic_full_git_reference",
            return_value="refs/remotes/upstream/main",
        ):
            is_remote_tracking = commands_release._git_reference_is_remote_tracking(
                repo_root=Path("/tmp/repo"),
                git_reference="upstream/main",
            )

        self.assertTrue(is_remote_tracking)

    def test_resolve_ship_source_git_ref_defaults_to_single_remote_main_when_origin_missing(self) -> None:
        source_git_ref = commands_release._resolve_ship_source_git_ref(
            source_git_ref_override="",
            target_definition=None,
            configured_remotes=("upstream",),
        )

        self.assertEqual(source_git_ref, "upstream/main")

    def test_infer_git_remote_from_reference_syntax_accepts_missing_remote_style_ref(self) -> None:
        remote_name = commands_release._infer_git_remote_from_reference_syntax(
            git_reference="upstream/main",
            configured_remotes=("origin", "upstream"),
        )

        self.assertEqual(remote_name, "upstream")

    def test_infer_git_remote_from_reference_syntax_rejects_explicit_refs_namespace(self) -> None:
        remote_name = commands_release._infer_git_remote_from_reference_syntax(
            git_reference="refs/heads/upstream/main",
            configured_remotes=("origin", "upstream"),
        )

        self.assertEqual(remote_name, "")

    def test_execute_ship_dry_run_skips_branch_sync_preflight(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
        )
        source_of_truth = self._source_of_truth(target_definition)

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
            )

        run_ship_branch_sync.assert_not_called()

    def test_execute_ship_syncs_compose_branch_before_deploying(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            temporary_directory = Path(temporary_directory_name)
            remote_directory = temporary_directory / "origin.git"
            repository_directory = temporary_directory / "repo"

            subprocess.run(["git", "init", "--bare", str(remote_directory)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "init", str(repository_directory)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "config", "user.email", "ship-tests@example.com"],
                cwd=repository_directory,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Ship Tests"],
                cwd=repository_directory,
                check=True,
                capture_output=True,
                text=True,
            )

            first_commit = self._commit_file(
                repository_directory=repository_directory,
                relative_path="tracked.txt",
                content="validated-commit-one\n",
                message="Initial validated commit",
            )
            subprocess.run(["git", "branch", "-M", "main"], cwd=repository_directory, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "remote", "add", "origin", str(remote_directory)],
                cwd=repository_directory,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=repository_directory, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "push", "origin", f"{first_commit}:refs/heads/cm-dev"],
                cwd=repository_directory,
                check=True,
                capture_output=True,
                text=True,
            )

            second_commit = self._commit_file(
                repository_directory=repository_directory,
                relative_path="tracked.txt",
                content="validated-commit-two\n",
                message="Validated commit for shipping",
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=repository_directory, check=True, capture_output=True, text=True)

            target_definition = DokployTargetDefinition(
                context="cm",
                instance="dev",
                target_type="compose",
                target_id="compose-id",
                target_name="cm-dev",
                git_branch="cm-dev",
            )
            source_of_truth = self._source_of_truth(target_definition)
            emitted_lines: list[str] = []
            deployed_paths: list[str] = []

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
                discover_repo_root_fn=lambda _path: repository_directory,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repository_directory / ".env", {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **kwargs: deployed_paths.append(str(kwargs.get("path", ""))) or {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=emitted_lines.append,
            )

            updated_remote_commit = subprocess.run(
                ["git", "--git-dir", str(remote_directory), "rev-parse", "refs/heads/cm-dev"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(updated_remote_commit, second_commit)
            self.assertEqual(deployed_paths, ["/api/compose.deploy"])
            self.assertIn("branch_sync=true", emitted_lines)
            self.assertIn("branch_sync_target_remote=origin", emitted_lines)
            self.assertIn("branch_sync_source_ref=origin/main", emitted_lines)
            self.assertIn("branch_sync_applied=true", emitted_lines)

    def test_run_ship_branch_sync_uses_single_configured_remote_when_origin_is_missing(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="upstream/main",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "upstream\n"
            if command == ["git", "fetch", "upstream", "--prune"]:
                return ""
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "upstream", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "upstream", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(
                commands_release,
                "_resolve_symbolic_full_git_reference",
                return_value="refs/remotes/upstream/main",
            ):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=False):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "fetch", "upstream", "--prune"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "upstream", "refs/heads/cm-dev"],
                ["git", "push", "upstream", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_run_ship_branch_sync_fetches_missing_remote_style_ref_even_without_local_tracking_ref(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="upstream/main",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "origin\nupstream\n"
            if command == ["git", "fetch", "upstream", "--prune"]:
                return ""
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(commands_release, "_resolve_symbolic_full_git_reference", return_value=""):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=False):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "fetch", "upstream", "--prune"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "origin", "refs/heads/cm-dev"],
                ["git", "push", "origin", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_run_ship_branch_sync_defaults_to_single_remote_main_when_origin_missing(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="dev",
            target_type="compose",
            target_id="compose-id",
            target_name="cm-dev",
            git_branch="cm-dev",
            source_git_ref="",
        )
        captured_commands: list[list[str]] = []

        def run_command_capture(command: list[str], *, repo_root: Path) -> str:
            self.assertEqual(repo_root, Path("/tmp/repo"))
            captured_commands.append(command)
            if command == ["git", "remote"]:
                return "upstream\n"
            if command == ["git", "fetch", "upstream", "--prune"]:
                return ""
            if command == ["git", "rev-parse", "--verify", "upstream/main^{commit}"]:
                return "abc123\n"
            if command == ["git", "ls-remote", "--heads", "upstream", "refs/heads/cm-dev"]:
                return "def456\trefs/heads/cm-dev\n"
            if command == ["git", "push", "upstream", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"]:
                return ""
            raise AssertionError(f"unexpected command: {command}")

        with patch.object(commands_release, "_run_command_capture", side_effect=run_command_capture):
            with patch.object(commands_release, "_resolve_symbolic_full_git_reference", return_value=""):
                with patch.object(commands_release, "_git_reference_exists_locally", return_value=False):
                    commands_release._run_ship_branch_sync(
                        repo_root=Path("/tmp/repo"),
                        source_git_ref_override="",
                        target_definition=target_definition,
                        echo_fn=lambda _line: None,
                    )

        self.assertEqual(
            captured_commands,
            [
                ["git", "remote"],
                ["git", "fetch", "upstream", "--prune"],
                ["git", "rev-parse", "--verify", "upstream/main^{commit}"],
                ["git", "ls-remote", "--heads", "upstream", "refs/heads/cm-dev"],
                ["git", "push", "upstream", "--force-with-lease=refs/heads/cm-dev:def456", "abc123:refs/heads/cm-dev"],
            ],
        )

    def test_execute_ship_requires_git_branch_for_compose_target(self) -> None:
        target_definition = self._target_definition(git_branch="")
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("deploy should not run")),
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
            )

        self.assertIn("requires git_branch", captured_error.exception.message)

    def test_execute_ship_passes_source_ref_override_to_branch_sync(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root_path = Path(temporary_directory_name)
            (repo_root_path / ".git").mkdir()
            target_definition = self._target_definition(git_branch="cm-dev")
            source_of_truth = self._source_of_truth(target_definition)
            captured_source_refs: list[str] = []

            def run_ship_branch_sync(
                *,
                repo_root: Path,
                source_git_ref_override: str,
                target_definition: DokployTargetDefinition | None,
                echo_fn: Callable[[str], None],
            ) -> None:
                self.assertEqual(repo_root, repo_root_path)
                self.assertIsNotNone(target_definition)
                captured_source_refs.append(source_git_ref_override)
                echo_fn("branch_sync=true")

            with (
                patch.object(commands_release, "_prepare_ship_branch_sync", return_value=None),
                patch.object(commands_release, "_run_ship_branch_sync", side_effect=run_ship_branch_sync),
            ):
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
                    discover_repo_root_fn=lambda _path: repo_root_path,
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root_path / ".env", {}),
                    load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                    find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                    resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                    resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                    resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                    run_required_gates_fn=lambda **_kwargs: None,
                    resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                    read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                    resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                    dokploy_request_fn=lambda **_kwargs: {},
                    latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                    deployment_key_fn=lambda _deployment: "",
                    wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                    verify_ship_healthchecks_fn=lambda **_kwargs: None,
                    latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                    wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                    echo_fn=lambda _line: None,
                    source_git_ref="feature-commit",
                )

            self.assertEqual(captured_source_refs, ["feature-commit"])

    def test_execute_ship_application_target_uses_source_ref_override_for_branch_sync(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root_path = Path(temporary_directory_name)
            (repo_root_path / ".git").mkdir()
            target_definition = self._target_definition(target_type="application", git_branch="cm-app")
            source_of_truth = self._source_of_truth(target_definition)
            captured_source_refs: list[str] = []

            def run_ship_branch_sync(
                *,
                repo_root: Path,
                source_git_ref_override: str,
                target_definition: DokployTargetDefinition | None,
                echo_fn: Callable[[str], None],
            ) -> None:
                self.assertEqual(repo_root, repo_root_path)
                self.assertIsNotNone(target_definition)
                captured_source_refs.append(source_git_ref_override)
                echo_fn("branch_sync=true")

            with (
                patch.object(commands_release, "_prepare_ship_branch_sync", return_value=None),
                patch.object(commands_release, "_run_ship_branch_sync", side_effect=run_ship_branch_sync),
            ):
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
                    discover_repo_root_fn=lambda _path: repo_root_path,
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root_path / ".env", {}),
                    load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                    find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                    resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                    resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                    resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                    run_required_gates_fn=lambda **_kwargs: None,
                    resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "application",
                    read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                    resolve_dokploy_target_fn=lambda **_kwargs: ("application", "application-id", "application-name", None, None),
                    dokploy_request_fn=lambda **_kwargs: {},
                    latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                    deployment_key_fn=lambda _deployment: "",
                    wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                    verify_ship_healthchecks_fn=lambda **_kwargs: None,
                    latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                    wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                    echo_fn=lambda _line: None,
                    source_git_ref="feature-commit",
                )

            self.assertEqual(captured_source_refs, ["feature-commit"])

    def test_execute_ship_application_target_with_git_branch_runs_branch_sync_without_source_override(self) -> None:
        target_definition = self._target_definition(target_type="application", git_branch="cm-app")
        source_of_truth = self._source_of_truth(target_definition)
        captured_source_refs: list[str] = []

        def run_ship_branch_sync(
            *,
            repo_root: Path,
            source_git_ref_override: str,
            target_definition: DokployTargetDefinition | None,
            echo_fn: Callable[[str], None],
        ) -> None:
            self.assertEqual(repo_root, Path("/tmp"))
            self.assertIsNotNone(target_definition)
            captured_source_refs.append(source_git_ref_override)
            echo_fn("branch_sync=true")

        with patch.object(commands_release, "_run_ship_branch_sync", side_effect=run_ship_branch_sync):
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "application",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("application", "application-id", "application-name", None, None),
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
            )

        self.assertEqual(captured_source_refs, [""])

    def test_execute_ship_runs_branch_sync_after_required_gates_for_source_ref_override(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()

            target_definition = self._target_definition(git_branch="cm-dev")
            source_of_truth = self._source_of_truth(target_definition)
            call_order: list[str] = []

            pinned_plan = commands_release.ShipBranchSyncPlan(
                source_git_ref="feature-commit",
                source_commit="pinned-sha",
                target_remote_name="origin",
                target_branch="cm-dev",
                remote_branch_commit_before="before-sha",
                branch_update_required=True,
            )

            def run_required_gates(**_kwargs: object) -> None:
                call_order.append("gates")

            def dokploy_request(**_kwargs: object) -> JsonObject:
                call_order.append("deploy")
                return {}

            with (
                patch.object(
                    commands_release,
                    "_prepare_ship_branch_sync",
                    side_effect=lambda **_kwargs: call_order.append("prepare") or pinned_plan,
                ),
                patch.object(
                    commands_release,
                    "_apply_ship_branch_sync",
                    side_effect=lambda **_kwargs: call_order.append("branch_sync"),
                ),
            ):
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
                    discover_repo_root_fn=lambda _path: repo_root,
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", {}),
                    load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                    find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                    resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                    resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                    resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                    run_required_gates_fn=run_required_gates,
                    resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                    read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                    resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                    dokploy_request_fn=dokploy_request,
                    latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                    deployment_key_fn=lambda _deployment: "",
                    wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                    verify_ship_healthchecks_fn=lambda **_kwargs: None,
                    latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                    wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                    echo_fn=lambda _line: None,
                    source_git_ref="feature-commit",
                )

            self.assertEqual(call_order, ["prepare", "gates", "branch_sync", "deploy"])

    def test_execute_ship_does_not_run_branch_sync_when_required_gates_fail(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root_path = Path(temporary_directory_name)
            (repo_root_path / ".git").mkdir()
            target_definition = self._target_definition(git_branch="cm-dev")
            source_of_truth = self._source_of_truth(target_definition)

            with (
                patch.object(commands_release, "_prepare_ship_branch_sync", return_value=None),
                patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync,
            ):
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
                        discover_repo_root_fn=lambda _path: repo_root_path,
                        load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root_path / ".env", {}),
                        load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                        find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                        resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                        resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                        resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                        run_required_gates_fn=lambda **_kwargs: (_ for _ in ()).throw(click.ClickException("gate failed")),
                        resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                        read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                        resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                        dokploy_request_fn=lambda **_kwargs: {},
                        latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                        deployment_key_fn=lambda _deployment: "",
                        wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                        verify_ship_healthchecks_fn=lambda **_kwargs: None,
                        latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                        wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                        echo_fn=lambda _line: None,
                        source_git_ref="feature-commit",
                    )

            self.assertEqual(captured_error.exception.message, "gate failed")
            run_ship_branch_sync.assert_not_called()

    def test_execute_ship_requires_git_metadata_before_gates_when_explicit_source_ref_must_be_pinned(self) -> None:
        target_definition = self._target_definition(git_branch="cm-dev")
        source_of_truth = self._source_of_truth(target_definition)
        gates_ran: list[str] = []

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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: gates_ran.append("gate"),
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
                source_git_ref="feature-commit",
            )

        self.assertIn("requires git metadata", captured_error.exception.message)
        self.assertEqual(gates_ran, [])

    def test_execute_export_ship_request_rejects_ship_mode_target_mismatch(self) -> None:
        target_definition = self._target_definition(context_name="opw", instance_name="prod", target_type="application").model_copy(
            update={"domains": ("prod.example.com",), "source_git_ref": "origin/opw-prod"}
        )
        source_of_truth = self._source_of_truth(target_definition)

        with self.assertRaises(click.ClickException) as captured_error:
            commands_release.execute_export_ship_request(
                context_name="opw",
                instance_name="prod",
                artifact_id="artifact-sha256-image456",
                env_file=None,
                source_git_ref="",
                wait=True,
                timeout_override_seconds=600,
                verify_health=True,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                allow_dirty=False,
                default_source_git_ref="origin/main",
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 45,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://prod.example.com/web/health",),
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                emit_payload_fn=lambda _payload: None,
            )

        self.assertIn("ship_mode=compose", captured_error.exception.message)
        self.assertIn("target_type=application", captured_error.exception.message)

    def test_execute_promote_passes_allow_dirty_through_to_ship(self) -> None:
        source_target_definition = self._target_definition(context_name="opw", instance_name="testing").model_copy(
            update={"git_branch": "opw-testing"}
        )
        destination_target_definition = self._target_definition(context_name="opw", instance_name="prod").model_copy(
            update={"git_branch": "opw-prod"}
        )
        source_of_truth = DokploySourceOfTruth(
            schema_version=1,
            targets=(source_target_definition, destination_target_definition),
        )
        captured_invocations: list[tuple[str, dict[str, object]]] = []
        emitted_lines: list[str] = []

        def invoke_platform_command(invoked_command_name: str, **kwargs: object) -> None:
            captured_invocations.append((invoked_command_name, dict(kwargs)))

        release_workflows.execute_promote(
            context_name="opw",
            from_instance_name="testing",
            to_instance_name="prod",
            env_file=None,
            wait=True,
            timeout_override_seconds=600,
            verify_health=True,
            health_timeout_override_seconds=60,
            verify_source_health=False,
            source_health_timeout_override_seconds=None,
            dry_run=True,
            no_cache=False,
            allow_dirty=True,
            assert_promote_path_allowed_fn=lambda **_kwargs: None,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda dokploy_source_of_truth, **kwargs: next(
                (
                    target_definition
                    for target_definition in dokploy_source_of_truth.targets
                    if target_definition.context == kwargs["context_name"] and target_definition.instance == kwargs["instance_name"]
                ),
                None,
            ),
            run_command_fn=lambda _command: None,
            resolve_remote_git_branch_commit_fn=lambda _remote_name, _branch_name: "abc123",
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://opw-testing.example/web/health",),
            collect_environment_gate_results_fn=lambda **_kwargs: [
                {"url": "https://opw-testing.example/web/health", "result": "pass"}
            ],
            run_production_backup_gate_fn=lambda **_kwargs: None,
            invoke_platform_command_fn=invoke_platform_command,
            echo_fn=emitted_lines.append,
        )

        self.assertEqual(
            emitted_lines,
            [
                "promote_context=opw",
                "promote_from_instance=testing",
                "promote_to_instance=prod",
                "promote_source_branch=opw-testing",
                "promote_source_commit=abc123",
                "promote_destination_branch=opw-prod",
                "prod_backup_gate=true",
            ],
        )
        self.assertEqual(len(captured_invocations), 1)
        command_name, command_kwargs = captured_invocations[0]
        self.assertEqual(command_name, "ship")
        self.assertEqual(command_kwargs["context_name"], "opw")
        self.assertEqual(command_kwargs["instance_name"], "prod")
        self.assertEqual(command_kwargs["skip_gate"], True)
        self.assertEqual(command_kwargs["allow_dirty"], True)
        self.assertEqual(command_kwargs["source_git_ref"], "abc123")

    def test_execute_promote_skips_git_fetch_on_dry_run(self) -> None:
        source_target_definition = self._target_definition(context_name="opw", instance_name="testing").model_copy(
            update={"git_branch": "opw-testing"}
        )
        destination_target_definition = self._target_definition(context_name="opw", instance_name="prod").model_copy(
            update={"git_branch": "opw-prod"}
        )
        source_of_truth = DokploySourceOfTruth(
            schema_version=1,
            targets=(source_target_definition, destination_target_definition),
        )
        captured_commands: list[list[str]] = []

        release_workflows.execute_promote(
            context_name="opw",
            from_instance_name="testing",
            to_instance_name="prod",
            env_file=None,
            wait=True,
            timeout_override_seconds=600,
            verify_health=True,
            health_timeout_override_seconds=60,
            verify_source_health=False,
            source_health_timeout_override_seconds=None,
            dry_run=True,
            no_cache=False,
            allow_dirty=False,
            assert_promote_path_allowed_fn=lambda **_kwargs: None,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda dokploy_source_of_truth, **kwargs: next(
                (
                    target_definition
                    for target_definition in dokploy_source_of_truth.targets
                    if target_definition.context == kwargs["context_name"] and target_definition.instance == kwargs["instance_name"]
                ),
                None,
            ),
            run_command_fn=lambda command: captured_commands.append(command),
            resolve_remote_git_branch_commit_fn=lambda _remote_name, _branch_name: "abc123",
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://opw-testing.example/web/health",),
            collect_environment_gate_results_fn=lambda **_kwargs: [],
            run_production_backup_gate_fn=lambda **_kwargs: None,
            invoke_platform_command_fn=lambda _command_name, **_kwargs: None,
            echo_fn=lambda _line: None,
        )

        self.assertEqual(captured_commands, [])

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

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-dev.example/web/health",),
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
                dokploy_request_fn=dokploy_request,
                latest_deployment_for_compose_fn=latest_deployment
                if target_type == "compose"
                else lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda deployment: str(deployment.get("id", "")) if isinstance(deployment, dict) else "",
                wait_for_dokploy_compose_deployment_fn=wait_for_deployment if target_type == "compose" else lambda **_kwargs: "",
                verify_ship_healthchecks_fn=lambda **_kwargs: None,
                latest_deployment_for_application_fn=latest_deployment
                if target_type == "application"
                else lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=wait_for_deployment if target_type == "application" else lambda **_kwargs: "",
                echo_fn=emitted_lines.append,
            )

        if target_type == "compose":
            run_ship_branch_sync.assert_called_once()
        else:
            run_ship_branch_sync.assert_not_called()

        self.assertEqual(call_order, ["latest_before", "deploy", "wait"])
        self.assertIn("deployment=after status=done", emitted_lines)

    def test_execute_ship_passes_source_of_truth_target_definition_to_target_resolution(self) -> None:
        emitted_lines: list[str] = []
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)
        seen_target_definitions: list[DokployTargetDefinition | None] = []

        def resolve_target(**kwargs: object) -> tuple[str, str, str, click.ClickException | None, click.ClickException | None]:
            target_definition_value = kwargs.get("target_definition")
            if target_definition_value is not None:
                self.assertIsInstance(target_definition_value, DokployTargetDefinition)
            typed_target_definition = (
                target_definition_value if isinstance(target_definition_value, DokployTargetDefinition) else None
            )
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
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=resolve_target,
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
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=load_environment,
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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

        run_ship_branch_sync.assert_called_once()

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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: None,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: None,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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
        source_of_truth = self._source_of_truth(self._target_definition(instance_name="testing"))

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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: None,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
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

    def test_execute_ship_runs_post_deploy_update_before_health_verification(self) -> None:
        call_order: list[str] = []
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
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
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-testing.example/web/health",),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **_kwargs: call_order.append("deploy") or {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: {"id": "before"},
                deployment_key_fn=lambda deployment: str(deployment.get("id", "")) if isinstance(deployment, dict) else "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: call_order.append("wait") or "deployment=after status=done",
                verify_ship_healthchecks_fn=lambda **_kwargs: call_order.append("health"),
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
                run_post_deploy_update_fn=lambda: call_order.append("update"),
            )

        run_ship_branch_sync.assert_called_once()

        self.assertEqual(call_order, ["deploy", "wait", "update", "health"])

    def test_execute_ship_no_wait_skips_post_deploy_update(self) -> None:
        target_definition = self._target_definition()
        source_of_truth = self._source_of_truth(target_definition)
        post_deploy_updates: list[str] = []

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
            commands_release.execute_ship(
                context_name="cm",
                instance_name="testing",
                env_file=None,
                wait=False,
                timeout_override_seconds=None,
                verify_health=True,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                skip_gate=True,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-testing.example/web/health",),
                run_required_gates_fn=lambda **_kwargs: None,
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                dokploy_request_fn=lambda **_kwargs: {},
                latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                deployment_key_fn=lambda _deployment: "",
                wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: (_ for _ in ()).throw(
                    AssertionError("wait should not run")
                ),
                verify_ship_healthchecks_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("health should not run")),
                latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                echo_fn=lambda _line: None,
                run_post_deploy_update_fn=lambda: post_deploy_updates.append("update"),
            )

        run_ship_branch_sync.assert_called_once()

        self.assertEqual(post_deploy_updates, [])

    def test_execute_ship_application_target_skips_post_deploy_update(self) -> None:
        target_definition = self._target_definition(target_type="application")
        source_of_truth = self._source_of_truth(target_definition)
        call_order: list[str] = []
        emitted_lines: list[str] = []

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
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-testing.example/web/health",),
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "application",
            read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
            resolve_dokploy_target_fn=lambda **_kwargs: ("application", "application-id", "application-name", None, None),
            dokploy_request_fn=lambda **_kwargs: call_order.append("deploy") or {},
            latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
            deployment_key_fn=lambda deployment: str(deployment.get("id", "")) if isinstance(deployment, dict) else "",
            wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "",
            verify_ship_healthchecks_fn=lambda **_kwargs: call_order.append("health"),
            latest_deployment_for_application_fn=lambda _host, _token, _application_id: {"id": "before"},
            wait_for_dokploy_deployment_fn=lambda **_kwargs: call_order.append("wait") or "deployment=after status=done",
            echo_fn=emitted_lines.append,
            run_post_deploy_update_fn=lambda: call_order.append("update"),
        )

        self.assertEqual(call_order, ["deploy", "wait", "health"])
        self.assertIn("post_deploy_update=skipped target_type=application", emitted_lines)

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
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
            find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
            resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
            resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
            resolve_ship_healthcheck_urls_fn=lambda **_kwargs: ("https://cm-testing.example/web/health",),
            run_required_gates_fn=lambda **_kwargs: None,
            resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
            read_dokploy_config_fn=lambda _environment_values: (_ for _ in ()).throw(click.ClickException("missing dokploy config")),
            resolve_dokploy_target_fn=lambda **_kwargs: ("", "", "", None, None),
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
        post_deploy_updates: list[str] = []

        with patch.object(commands_release, "_run_ship_branch_sync") as run_ship_branch_sync:
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
                    discover_repo_root_fn=lambda _path: Path("/tmp"),
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                    load_dokploy_source_of_truth_if_present_fn=lambda _repo_root: source_of_truth,
                    find_dokploy_target_definition_fn=lambda *_args, **_kwargs: target_definition,
                    resolve_ship_timeout_seconds_fn=lambda **_kwargs: 600,
                    resolve_ship_health_timeout_seconds_fn=lambda **_kwargs: 60,
                    resolve_ship_healthcheck_urls_fn=lambda **_kwargs: (),
                    run_required_gates_fn=lambda **_kwargs: None,
                    resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "compose",
                    read_dokploy_config_fn=lambda _environment_values: ("https://dokploy.example", "token"),
                    resolve_dokploy_target_fn=lambda **_kwargs: ("compose", "compose-id", "compose-name", None, None),
                    dokploy_request_fn=lambda **_kwargs: {},
                    latest_deployment_for_compose_fn=lambda _host, _token, _compose_id: None,
                    deployment_key_fn=lambda _deployment: "",
                    wait_for_dokploy_compose_deployment_fn=lambda **_kwargs: "deployment=after status=done",
                    verify_ship_healthchecks_fn=lambda **_kwargs: None,
                    latest_deployment_for_application_fn=lambda _host, _token, _application_id: None,
                    wait_for_dokploy_deployment_fn=lambda **_kwargs: "",
                    echo_fn=emitted_lines.append,
                    run_post_deploy_update_fn=lambda: post_deploy_updates.append("update"),
                )

        run_ship_branch_sync.assert_called_once()

        self.assertEqual(post_deploy_updates, [])

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
