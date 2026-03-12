"""Regression tests for testkit docker helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.testkit import docker_api


class TestkitDockerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        docker_api._SCRIPT_RUNNER_SERVICE_BY_PROJECT.clear()

    def test_ensure_named_volume_permissions_applies_default_runtime_paths(self) -> None:
        run_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.docker_api.subprocess.run", return_value=run_result) as run_mock,
        ):
            docker_api.ensure_named_volume_permissions()

        self.assertEqual(run_mock.call_count, 1)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[:5], ["docker", "compose", "exec", "-T", "script-runner"])
        self.assertIn("/volumes/data", command[-1])
        self.assertIn("/volumes/data/filestore", command[-1])
        self.assertIn("/volumes/logs", command[-1])
        self.assertIn(".testkit_probe_", command[-1])

    def test_ensure_named_volume_permissions_honors_runtime_directory_overrides(self) -> None:
        run_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch(
                "tools.testkit.docker_api.compose_env",
                return_value={
                    "ODOO_PROJECT_NAME": "odoo-opw",
                    "ODOO_DATA_DIR": "/runtime/data",
                    "ODOO_LOG_DIR": "/runtime/logs",
                },
            ),
            patch("tools.testkit.docker_api.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.docker_api.subprocess.run", return_value=run_result) as run_mock,
        ):
            docker_api.ensure_named_volume_permissions()

        command = run_mock.call_args.args[0]
        self.assertIn("/runtime/data", command[-1])
        self.assertIn("/runtime/data/filestore", command[-1])
        self.assertIn("/runtime/logs", command[-1])

    def test_ensure_named_volume_permissions_normalizes_when_probe_fails(self) -> None:
        probe_failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="permission denied")
        normalized = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        verification_ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.get_script_runner_service", return_value="script-runner"),
            patch(
                "tools.testkit.docker_api.subprocess.run",
                side_effect=[probe_failed, normalized, verification_ok],
            ) as run_mock,
        ):
            docker_api.ensure_named_volume_permissions()

        self.assertEqual(run_mock.call_count, 3)
        normalization_command = run_mock.call_args_list[1].args[0]
        self.assertIn("--user", normalization_command)
        self.assertIn("root", normalization_command)
        self.assertIn("chown ubuntu:ubuntu", normalization_command[-1])
        self.assertIn("chmod ug+rwX", normalization_command[-1])

    def test_ensure_named_volume_permissions_raises_when_exec_fails(self) -> None:
        failed_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing container")
        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.docker_api.subprocess.run", return_value=failed_result),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                docker_api.ensure_named_volume_permissions()

        self.assertIn("Failed to normalize testkit volume permissions", str(error_context.exception))

    def test_ensure_services_up_checks_running_status_before_start(self) -> None:
        not_running_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        started_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="started", stderr="")

        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.subprocess.run", side_effect=[not_running_result, started_result]) as run_mock,
        ):
            docker_api.ensure_services_up(["script-runner"])

        self.assertEqual(run_mock.call_count, 2)
        status_command = run_mock.call_args_list[0].args[0]
        self.assertEqual(status_command, ["docker", "compose", "ps", "--status", "running", "-q", "script-runner"])
        start_command = run_mock.call_args_list[1].args[0]
        self.assertEqual(start_command, ["docker", "compose", "up", "-d", "script-runner"])

    def test_ensure_services_up_skips_start_for_running_service(self) -> None:
        running_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr="")

        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.subprocess.run", return_value=running_result) as run_mock,
        ):
            docker_api.ensure_services_up(["script-runner"])

        self.assertEqual(run_mock.call_count, 1)

    def test_ensure_services_up_raises_on_start_failure(self) -> None:
        not_running_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        start_failed_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.subprocess.run", side_effect=[not_running_result, start_failed_result]),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                docker_api.ensure_services_up(["script-runner"])

        self.assertIn("Failed to start service", str(error_context.exception))

    def test_cleanup_testkit_db_volume_removes_only_database_volume(self) -> None:
        with (
            patch(
                "tools.testkit.docker_api.compose_env",
                return_value={
                    "ODOO_PROJECT_NAME": "odoo-opw",
                    "TESTKIT_DB_VOLUME_CLEANUP": "1",
                },
            ),
            patch("tools.testkit.docker_api.subprocess.run") as run_mock,
        ):
            docker_api.cleanup_testkit_db_volume()

        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(run_mock.call_args.args[0], ["docker", "volume", "rm", "-f", "odoo-opw_testkit_db"])

    def test_cleanup_testkit_db_volume_noops_without_cleanup_flags(self) -> None:
        with (
            patch(
                "tools.testkit.docker_api.compose_env",
                return_value={
                    "ODOO_PROJECT_NAME": "odoo-opw",
                },
            ),
            patch("tools.testkit.docker_api.subprocess.run") as run_mock,
        ):
            docker_api.cleanup_testkit_db_volume()

        run_mock.assert_not_called()

    def test_get_script_runner_service_caches_by_project_name(self) -> None:
        process_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="database\nscript-runner\n",
            stderr="",
        )
        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.subprocess.run", return_value=process_result) as run_mock,
        ):
            first_service = docker_api.get_script_runner_service()
            second_service = docker_api.get_script_runner_service()

        self.assertEqual(first_service, "script-runner")
        self.assertEqual(second_service, "script-runner")
        self.assertEqual(run_mock.call_count, 1)

    def test_get_script_runner_service_does_not_cache_fallback_on_empty_discovery(self) -> None:
        empty_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        discovered_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="database\nmy-script-runner\n", stderr="")
        with (
            patch("tools.testkit.docker_api.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.docker_api.subprocess.run", side_effect=[empty_result, discovered_result]) as run_mock,
        ):
            first_service = docker_api.get_script_runner_service()
            second_service = docker_api.get_script_runner_service()

        self.assertEqual(first_service, "script-runner")
        self.assertEqual(second_service, "my-script-runner")
        self.assertEqual(run_mock.call_count, 2)

    def test_compose_env_defaults_state_root_under_platform_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("ODOO_STACK_NAME=cm-local\n", encoding="utf-8")

            with patch.dict("os.environ", {}, clear=True):
                with patch("tools.testkit.docker_api.Path.cwd", return_value=repo_root):
                    composed_environment = docker_api.compose_env()

        self.assertEqual(
            composed_environment["ODOO_STATE_ROOT"],
            str((repo_root / ".platform" / "state" / "cm-local").resolve()),
        )


if __name__ == "__main__":
    unittest.main()
