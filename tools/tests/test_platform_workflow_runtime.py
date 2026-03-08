"""Regression tests for platform workflow runtime command sequencing."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import click

from tools.deployer.command import CommandError
from tools.platform import workflow_runtime
from tools.platform.models import ContextDefinition, InstanceDefinition, LoadedStack, RuntimeSelection, StackDefinition


def _sample_runtime_context() -> tuple[StackDefinition, RuntimeSelection, dict[str, str], Path]:
    context_definition = ContextDefinition()
    instance_definition = InstanceDefinition()
    stack_definition = StackDefinition(
        schema_version=1,
        odoo_version="19.0",
        addons_path=("/odoo/addons", "/opt/project/addons"),
        contexts={"cm": context_definition},
    )
    runtime_selection = RuntimeSelection(
        context_name="cm",
        instance_name="local",
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name="cm",
        project_name="odoo-cm-local",
        state_path=Path("/tmp/.platform/state/cm/local"),
        data_mount=Path("/tmp/.platform/data/cm/local"),
        runtime_conf_host_path=Path("/tmp/.platform/runtime/cm.local.conf"),
        data_volume_name="odoo-cm-local-data",
        log_volume_name="odoo-cm-local-log",
        db_volume_name="odoo-cm-local-db",
        web_host_port=8069,
        longpoll_host_port=8072,
        db_host_port=5432,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=("cm_custom", "web_studio"),
        effective_addon_repositories=(),
        effective_runtime_env={},
    )
    loaded_environment = {
        "ODOO_DB_USER": "odoo",
        "ODOO_DB_PASSWORD": "database-password",
    }
    runtime_env_file = Path("/tmp/cm.local.env")
    return stack_definition, runtime_selection, loaded_environment, runtime_env_file


def _compose_base_command(runtime_env_file: Path) -> list[str]:
    return ["docker", "compose", "--env-file", str(runtime_env_file)]


def _sample_loaded_stack() -> LoadedStack:
    stack_definition, _, _, _ = _sample_runtime_context()
    return LoadedStack(
        stack_file_path=Path("platform/stack.toml"),
        stack_definition=stack_definition.model_copy(update={"contexts": {"opw": ContextDefinition()}}),
    )


def _sample_runtime_selection(context_name: str) -> RuntimeSelection:
    _, runtime_selection, _, _ = _sample_runtime_context()
    return RuntimeSelection(
        **{
            **runtime_selection.__dict__,
            "context_name": context_name,
        }
    )


def _load_sample_stack(_path: Path) -> LoadedStack:
    return _sample_loaded_stack()


def _resolve_sample_runtime_selection(
    _stack_definition: StackDefinition,
    context_name: str,
    _instance_name: str,
) -> RuntimeSelection:
    return _sample_runtime_selection(context_name)


def _write_sample_runtime_odoo_conf_file(
    _runtime_selection: RuntimeSelection,
    _stack_definition: StackDefinition,
    _loaded_environment: dict[str, str],
) -> Path:
    return Path("/tmp/platform.odoo.conf")


def _write_sample_runtime_env_file(
    _repo_root: Path,
    _stack_definition: StackDefinition,
    runtime_selection: RuntimeSelection,
    _loaded_environment: dict[str, str],
) -> Path:
    return Path(f"/tmp/{runtime_selection.context_name}.{runtime_selection.instance_name}.env")


def _raise_missing_upstream(
    _stack_name: str,
    *,
    env_file: Path | None,
    bootstrap_only: bool,
    no_sanitize: bool,
) -> int:
    _ = env_file
    _ = bootstrap_only
    _ = no_sanitize
    raise ValueError("missing upstream")


def _raise_restore_command_error(
    _stack_name: str,
    *,
    env_file: Path | None,
    bootstrap_only: bool,
    no_sanitize: bool,
) -> int:
    _ = env_file
    _ = bootstrap_only
    _ = no_sanitize
    raise CommandError(["restore-from-upstream"], 1, None, "restore failed")


def _assert_restore_workflow_raises_click_exception(
    test_case: unittest.TestCase,
    *,
    restore_stack_fn: Callable[..., int],
    expected_message_fragment: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        env_file = Path(temporary_directory) / "opw.local.env"
        env_file.write_text("KEY=value\n", encoding="utf-8")
        with test_case.assertRaises(click.ClickException) as error_context:
            workflow_runtime.run_restore_workflow(
                repo_root=Path(temporary_directory),
                stack_file=Path("platform/stack.toml"),
                context_name="opw",
                instance_name="local",
                env_file=env_file,
                bootstrap_only=False,
                no_sanitize=False,
                dry_run=False,
                load_stack_fn=_load_sample_stack,
                resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
                load_environment_fn=lambda *_args, **_kwargs: (Path("/tmp/.env"), {}),
                write_runtime_odoo_conf_file_fn=_write_sample_runtime_odoo_conf_file,
                write_runtime_env_file_fn=_write_sample_runtime_env_file,
                restore_stack_fn=restore_stack_fn,
                echo_fn=lambda _message: None,
            )

    test_case.assertIn(expected_message_fragment, str(error_context.exception))


class PlatformWorkflowRuntimeTests(unittest.TestCase):
    def test_apply_admin_password_defaults_login_to_admin(self) -> None:
        captured_input: dict[str, object] = {}

        def run_command_with_input(command: list[str], input_text: str) -> None:
            captured_input["command"] = command
            captured_input["input_text"] = input_text

        echo_messages: list[str] = []
        stack_definition, runtime_selection, loaded_environment, runtime_env_file = _sample_runtime_context()
        loaded_environment["ODOO_ADMIN_PASSWORD"] = "secure-password"

        workflow_runtime._apply_admin_password_if_configured(
            runtime_env_file,
            runtime_selection,
            stack_definition,
            loaded_environment,
            compose_base_command_fn=_compose_base_command,
            run_command_with_input_fn=run_command_with_input,
            echo_fn=echo_messages.append,
        )

        self.assertIn("admin_password_action=defaulted_odoo_admin_login=admin", echo_messages)
        self.assertIn('"login": "admin"', str(captured_input["input_text"]))

    def test_admin_password_policy_checks_admin_even_without_configured_login(self) -> None:
        captured_input: dict[str, object] = {}
        stack_definition, runtime_selection, loaded_environment, runtime_env_file = _sample_runtime_context()

        workflow_runtime._assert_active_admin_password_is_not_default(
            runtime_env_file,
            runtime_selection,
            stack_definition,
            loaded_environment,
            compose_base_command_fn=_compose_base_command,
            run_command_with_input_fn=lambda command, input_text: captured_input.update(
                {"command": command, "input_text": input_text}
            ),
        )

        self.assertIn('"logins": ["admin"]', str(captured_input["input_text"]))

    def test_admin_password_policy_checks_configured_login_in_addition_to_admin(self) -> None:
        captured_input: dict[str, object] = {}
        stack_definition, runtime_selection, loaded_environment, runtime_env_file = _sample_runtime_context()
        loaded_environment["ODOO_ADMIN_LOGIN"] = "root-admin"

        workflow_runtime._assert_active_admin_password_is_not_default(
            runtime_env_file,
            runtime_selection,
            stack_definition,
            loaded_environment,
            compose_base_command_fn=_compose_base_command,
            run_command_with_input_fn=lambda command, input_text: captured_input.update(
                {"command": command, "input_text": input_text}
            ),
        )

        rendered_input = str(captured_input["input_text"])
        self.assertIn('"admin"', rendered_input)
        self.assertIn('"root-admin"', rendered_input)

    def test_run_init_workflow_dry_run_starts_script_runner_before_exec(self) -> None:
        captured_dry_run_commands: list[list[str]] = []

        def capture_web_pause_call(
            *_args: object,
            dry_run: bool,
            dry_run_commands: tuple[list[str], ...],
            **_kwargs: object,
        ) -> None:
            self.assertTrue(dry_run)
            nonlocal captured_dry_run_commands
            captured_dry_run_commands = list(dry_run_commands)

        with (
            patch(
                "tools.platform.workflow_runtime._load_command_runtime_context",
                return_value=_sample_runtime_context(),
            ),
            patch(
                "tools.platform.workflow_runtime._run_with_web_temporarily_stopped",
                side_effect=capture_web_pause_call,
            ),
        ):
            workflow_runtime.run_init_workflow(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=True,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_stack_fn=_load_sample_stack,
                resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                compose_base_command_fn=_compose_base_command,
                run_command_fn=lambda _command: None,
                run_command_best_effort_fn=lambda _command: 0,
                run_command_with_input_fn=lambda _command, _input_text: None,
                echo_fn=lambda _message: None,
            )

        self.assertEqual(len(captured_dry_run_commands), 2)
        self.assertEqual(captured_dry_run_commands[0][-3:], ["up", "-d", "script-runner"])
        self.assertEqual(captured_dry_run_commands[1][4:7], ["exec", "-T", "script-runner"])

    def test_run_update_workflow_starts_script_runner_before_exec(self) -> None:
        executed_commands: list[list[str]] = []

        def run_command(command: list[str]) -> None:
            executed_commands.append(command)

        def run_web_pause_operation(
            *_args: object,
            operation: Callable[[], None],
            **_kwargs: object,
        ) -> None:
            operation()

        with (
            patch(
                "tools.platform.workflow_runtime._load_command_runtime_context",
                return_value=_sample_runtime_context(),
            ),
            patch(
                "tools.platform.workflow_runtime._run_with_web_temporarily_stopped",
                side_effect=run_web_pause_operation,
            ),
        ):
            workflow_runtime.run_update_workflow(
                stack_file=Path("platform/stack.toml"),
                context_name="cm",
                instance_name="local",
                env_file=None,
                dry_run=False,
                discover_repo_root_fn=lambda _path: Path("/tmp"),
                load_stack_fn=_load_sample_stack,
                resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
                compose_base_command_fn=_compose_base_command,
                run_command_fn=run_command,
                run_command_best_effort_fn=lambda _command: 0,
                echo_fn=lambda _message: None,
            )

        self.assertEqual(len(executed_commands), 2)
        self.assertEqual(executed_commands[0][-3:], ["up", "-d", "script-runner"])
        self.assertEqual(executed_commands[1][4:7], ["exec", "-T", "script-runner"])

    def test_run_restore_workflow_wraps_value_errors_as_click_exception(self) -> None:
        _assert_restore_workflow_raises_click_exception(
            self,
            restore_stack_fn=_raise_missing_upstream,
            expected_message_fragment="missing upstream",
        )

    def test_run_restore_workflow_wraps_command_errors_as_click_exception(self) -> None:
        _assert_restore_workflow_raises_click_exception(
            self,
            restore_stack_fn=_raise_restore_command_error,
            expected_message_fragment="command failed",
        )

    def test_run_restore_workflow_loads_environment_fail_closed_for_collisions(self) -> None:
        captured_collision_mode: dict[str, object] = {}

        def load_environment_with_capture(
            _repo_root: Path,
            _env_file: Path | None,
            **kwargs: object,
        ) -> tuple[Path, dict[str, str]]:
            captured_collision_mode["value"] = kwargs.get("collision_mode")
            return Path("/tmp/.env"), {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            stack_file = repo_root / "platform" / "stack.toml"
            stack_file.parent.mkdir(parents=True)
            stack_file.write_text("schema_version = 1\n", encoding="utf-8")

            workflow_runtime.run_restore_workflow(
                repo_root=repo_root,
                stack_file=Path("platform/stack.toml"),
                context_name="opw",
                instance_name="local",
                env_file=None,
                bootstrap_only=False,
                no_sanitize=False,
                dry_run=True,
                load_stack_fn=_load_sample_stack,
                resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
                load_environment_fn=load_environment_with_capture,
                write_runtime_odoo_conf_file_fn=_write_sample_runtime_odoo_conf_file,
                write_runtime_env_file_fn=_write_sample_runtime_env_file,
                restore_stack_fn=lambda *_args, **_kwargs: 0,
                echo_fn=lambda _message: None,
            )

        self.assertEqual(captured_collision_mode.get("value"), "error")

    def test_run_workflow_select_invokes_platform_select_with_dry_run_false(self) -> None:
        captured_invocations: list[tuple[str, dict[str, object]]] = []

        def invoke_platform_command(invoked_command_name: str, **kwargs: object) -> None:
            captured_invocations.append((invoked_command_name, kwargs))

        workflow_runtime.run_workflow(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="local",
            env_file=None,
            workflow="select",
            dry_run=False,
            no_cache=False,
            bootstrap_only=False,
            no_sanitize=False,
            force=False,
            reset_versions=False,
            allow_prod_data_workflow=False,
            assert_prod_data_workflow_allowed_fn=lambda **_kwargs: None,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_stack_fn=_load_sample_stack,
            resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            write_runtime_odoo_conf_file_fn=_write_sample_runtime_odoo_conf_file,
            write_runtime_env_file_fn=_write_sample_runtime_env_file,
            restore_stack_fn=lambda *_args, **_kwargs: 0,
            compose_base_command_fn=_compose_base_command,
            run_command_fn=lambda _command: None,
            run_command_best_effort_fn=lambda _command: 0,
            run_command_with_input_fn=lambda _command, _input_text: None,
            invoke_platform_command_fn=invoke_platform_command,
            echo_fn=lambda _message: None,
        )

        self.assertEqual(len(captured_invocations), 1)
        command_name, invocation_kwargs = captured_invocations[0]
        self.assertEqual(command_name, "select")
        self.assertEqual(invocation_kwargs["dry_run"], False)

    def test_run_workflow_up_invokes_platform_up_with_build_images(self) -> None:
        captured_invocations: list[tuple[str, dict[str, object]]] = []

        def invoke_platform_command(invoked_command_name: str, **kwargs: object) -> None:
            captured_invocations.append((invoked_command_name, kwargs))

        workflow_runtime.run_workflow(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="local",
            env_file=None,
            workflow="up",
            dry_run=False,
            no_cache=True,
            bootstrap_only=False,
            no_sanitize=False,
            force=False,
            reset_versions=False,
            allow_prod_data_workflow=False,
            assert_prod_data_workflow_allowed_fn=lambda **_kwargs: None,
            discover_repo_root_fn=lambda _path: Path("/tmp"),
            load_stack_fn=_load_sample_stack,
            resolve_runtime_selection_fn=_resolve_sample_runtime_selection,
            load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (Path("/tmp/.env"), {}),
            write_runtime_odoo_conf_file_fn=_write_sample_runtime_odoo_conf_file,
            write_runtime_env_file_fn=_write_sample_runtime_env_file,
            restore_stack_fn=lambda *_args, **_kwargs: 0,
            compose_base_command_fn=_compose_base_command,
            run_command_fn=lambda _command: None,
            run_command_best_effort_fn=lambda _command: 0,
            run_command_with_input_fn=lambda _command, _input_text: None,
            invoke_platform_command_fn=invoke_platform_command,
            echo_fn=lambda _message: None,
        )

        self.assertEqual(len(captured_invocations), 1)
        command_name, invocation_kwargs = captured_invocations[0]
        self.assertEqual(command_name, "up")
        self.assertEqual(invocation_kwargs["build_images"], True)
        self.assertEqual(invocation_kwargs["no_cache"], True)


if __name__ == "__main__":
    unittest.main()
