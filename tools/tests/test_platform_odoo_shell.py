"""Targeted tests for the platform odoo-shell command helper."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from tools.platform import commands_lifecycle
from tools.tests.test_platform_commands import (
    _build_loaded_stack_for_test,
    _sample_runtime_selection,
    _sample_stack_definition,
)


class PlatformOdooShellTests(unittest.TestCase):
    @staticmethod
    def _runtime_env_values() -> dict[str, str]:
        return {"ODOO_DB_USER": "odoo", "ODOO_DB_PASSWORD": "pw"}

    @staticmethod
    def _runtime_state_path(repo_root: Path) -> Path:
        return repo_root / ".platform" / "state" / "cm-local" / "platform.odoo.conf"

    @staticmethod
    def _runtime_env_file(repo_root: Path) -> Path:
        return repo_root / ".platform" / "env" / "cm.local.env"

    @staticmethod
    def _prepare_script_fixture(repo_root: Path) -> tuple[Path, Path]:
        script_path = repo_root / "tmp" / "scripts" / "probe.py"
        log_file = repo_root / "tmp" / "logs" / "probe.log"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("print('ok')\n", encoding="utf-8")
        return script_path, log_file

    @staticmethod
    def _unexpected_direct_runner(_command: list[str], _input_text: str) -> None:
        raise AssertionError("direct runner should not be used")

    @staticmethod
    def _unexpected_log_runner(_command: list[str], _input_text: str, _log_file: Path) -> None:
        raise AssertionError("log capture runner should not be used")

    @staticmethod
    def _unexpected_dry_run_direct_runner(_command: list[str], _input_text: str) -> None:
        raise AssertionError("runner should not be used in dry-run")

    @staticmethod
    def _unexpected_dry_run_log_runner(_command: list[str], _input_text: str, _log_file: Path) -> None:
        raise AssertionError("log runner should not be used in dry-run")

    def _execute_odoo_shell(
        self,
        *,
        repo_root: Path,
        loaded_stack,
        script_path: Path,
        service: str = "script-runner",
        database_name: str | None = None,
        log_file: Path | None = None,
        dry_run: bool = False,
        load_environment_fn=None,
        run_command_with_input_fn=None,
        run_command_with_input_to_log_fn=None,
        echo_fn=None,
    ) -> None:
        commands_lifecycle.execute_odoo_shell(
            stack_file=Path("platform/stack.toml"),
            context_name="cm",
            instance_name="local",
            env_file=None,
            script_path=script_path,
            service=service,
            database_name=database_name,
            log_file=log_file,
            dry_run=dry_run,
            discover_repo_root_fn=lambda _path: repo_root,
            load_stack_fn=lambda _path: loaded_stack,
            resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
            load_environment_fn=(
                load_environment_fn
                if load_environment_fn is not None
                else lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", self._runtime_env_values())
            ),
            write_runtime_odoo_conf_file_fn=lambda *_args, **_kwargs: self._runtime_state_path(repo_root),
            write_runtime_env_file_fn=lambda *_args, **_kwargs: self._runtime_env_file(repo_root),
            compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
            run_command_with_input_fn=(run_command_with_input_fn if run_command_with_input_fn is not None else lambda _command, _input_text: None),
            run_command_with_input_to_log_fn=(
                run_command_with_input_to_log_fn
                if run_command_with_input_to_log_fn is not None
                else lambda _command, _input_text, _log_file: None
            ),
            echo_fn=(echo_fn if echo_fn is not None else lambda _line: None),
        )

    def test_execute_odoo_shell_builds_expected_command(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            script_path, _log_file = self._prepare_script_fixture(repo_root)

            captured_commands: list[list[str]] = []
            captured_inputs: list[str] = []

            self._execute_odoo_shell(
                repo_root=repo_root,
                loaded_stack=loaded_stack,
                script_path=script_path,
                run_command_with_input_fn=lambda command, input_text: captured_commands.append(command) or captured_inputs.append(input_text),
                run_command_with_input_to_log_fn=self._unexpected_log_runner,
            )

            self.assertEqual(captured_inputs, ["print('ok')\n"])
            self.assertEqual(
                captured_commands,
                [
                    [
                        "docker",
                        "compose",
                        "exec",
                        "-T",
                        "script-runner",
                        "/odoo/odoo-bin",
                        "shell",
                        "-d",
                        "cm",
                        "--addons-path=/odoo/addons",
                        "--data-dir=/volumes/data",
                        "--db_host=database",
                        "--db_port=5432",
                        "--db_user=odoo",
                        "--db_password=pw",
                    ]
                ],
            )

    def test_execute_odoo_shell_uses_log_runner_when_log_file_requested(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            script_path, log_file = self._prepare_script_fixture(repo_root)

            captured_calls: list[tuple[list[str], str, Path]] = []

            self._execute_odoo_shell(
                repo_root=repo_root,
                loaded_stack=loaded_stack,
                script_path=script_path,
                database_name="custom_db",
                log_file=log_file,
                run_command_with_input_fn=self._unexpected_direct_runner,
                run_command_with_input_to_log_fn=lambda command, input_text, resolved_log_file: captured_calls.append(
                    (command, input_text, resolved_log_file)
                ),
            )

            self.assertEqual(len(captured_calls), 1)
            captured_command, captured_input, captured_log_file = captured_calls[0]
            self.assertEqual(captured_input, "print('ok')\n")
            self.assertEqual(captured_log_file, log_file)
            self.assertIn("custom_db", captured_command)

    def test_execute_odoo_shell_dry_run_emits_command(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            script_path, _log_file = self._prepare_script_fixture(repo_root)
            emitted_lines: list[str] = []

            self._execute_odoo_shell(
                repo_root=repo_root,
                loaded_stack=loaded_stack,
                script_path=script_path,
                log_file=Path("tmp/logs/probe.log"),
                dry_run=True,
                run_command_with_input_fn=self._unexpected_dry_run_direct_runner,
                run_command_with_input_to_log_fn=self._unexpected_dry_run_log_runner,
                echo_fn=emitted_lines.append,
            )

            self.assertTrue(any(line.startswith("odoo_shell_command=docker compose exec -T") for line in emitted_lines))

    def test_execute_odoo_shell_requires_script_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())

            with self.assertRaises(click.ClickException) as captured_error:
                self._execute_odoo_shell(
                    repo_root=repo_root,
                    loaded_stack=loaded_stack,
                    script_path=repo_root / "missing.py",
                    load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", {}),
                )

            self.assertIn("Script file not found", captured_error.exception.message)

    def test_execute_odoo_shell_resolves_relative_paths_from_repo_root(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            loaded_stack = _build_loaded_stack_for_test(repo_root, stack_definition=_sample_stack_definition())
            script_path, log_file = self._prepare_script_fixture(repo_root)

            captured_calls: list[tuple[list[str], str, Path]] = []

            self._execute_odoo_shell(
                repo_root=repo_root,
                loaded_stack=loaded_stack,
                script_path=Path("tmp/scripts/probe.py"),
                log_file=Path("tmp/logs/probe.log"),
                run_command_with_input_fn=self._unexpected_direct_runner,
                run_command_with_input_to_log_fn=lambda command, input_text, resolved_log_file: captured_calls.append(
                    (command, input_text, resolved_log_file)
                ),
            )

            self.assertEqual(len(captured_calls), 1)
            _, captured_input, captured_log_file = captured_calls[0]
            self.assertEqual(captured_input, "print('ok')\n")
            self.assertEqual(captured_log_file, log_file)


if __name__ == "__main__":
    unittest.main()
