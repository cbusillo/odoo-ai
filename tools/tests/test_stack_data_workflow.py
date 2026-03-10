"""Regression tests for stack data workflow environment propagation behavior."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import stack_data_workflow
from tools.deployer.settings import StackSettings


class StackDataWorkflowTests(unittest.TestCase):
    def test_data_workflow_script_environment_keeps_required_keys_and_prefixes(self) -> None:
        env_values = {
            "ODOO_DB_PASSWORD": "secret",
            "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
            "ENV_OVERRIDE_DISABLE_CRON": "true",
            "OPENUPGRADE_FORCE": "1",
            "UNRELATED": "drop-me",
        }

        filtered_values = stack_data_workflow._data_workflow_script_environment(env_values)

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

        stack_data_workflow._add_exec_env_names(command, ["ODOO_DB_PASSWORD", "ODOO_FILESTORE_PATH"])

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

    def test_resolve_data_workflow_environment_uses_process_env_for_missing_variable_references(self) -> None:
        previous_value = os.environ.get("RESTORE_TEST_SENTINEL")
        os.environ["RESTORE_TEST_SENTINEL"] = "host-value"
        try:
            resolved = stack_data_workflow._resolve_data_workflow_environment(
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

    def test_resolve_data_workflow_environment_uses_default_when_process_env_missing(self) -> None:
        previous_value = os.environ.get("RESTORE_TEST_MISSING")
        os.environ.pop("RESTORE_TEST_MISSING", None)
        try:
            resolved = stack_data_workflow._resolve_data_workflow_environment(
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

    def test_resolve_data_workflow_environment_substitutes_known_variables(self) -> None:
        resolved = stack_data_workflow._resolve_data_workflow_environment(
            {
                "BASE": "odoo",
                "IMAGE": "${BASE}:19",
            }
        )

        self.assertEqual(resolved["IMAGE"], "odoo:19")

    def test_resolve_data_workflow_environment_expands_dollar_style_env_variables(self) -> None:
        previous_value = os.environ.get("RESTORE_LEGACY_PATH")
        os.environ["RESTORE_LEGACY_PATH"] = "/tmp/legacy-restore"
        try:
            resolved = stack_data_workflow._resolve_data_workflow_environment(
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

    def test_resolve_data_workflow_environment_expands_home_directory_shorthand(self) -> None:
        resolved = stack_data_workflow._resolve_data_workflow_environment(
            {
                "HOME_STYLE_PATH": "~/restore-input",
            }
        )

        self.assertEqual(
            resolved["HOME_STYLE_PATH"],
            os.path.expanduser("~/restore-input"),
        )

    def test_missing_upstream_restore_keys_reports_only_empty_required_values(self) -> None:
        missing_keys = stack_data_workflow._missing_upstream_source_keys(
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

    def test_run_stack_data_workflow_does_not_route_unknown_hyphenated_stack_to_dokploy(self) -> None:
        stack_settings = StackSettings(
            name="custom-stack",
            repo_root=Path("/tmp/repo"),
            env_file=Path("/tmp/custom-stack.env"),
            source_env_file=Path("/tmp/custom-stack.env"),
            environment={"DOKPLOY_HOST": "https://dokploy.example"},
            state_root=Path("/tmp/state/custom-stack"),
            data_dir=Path("/tmp/state/custom-stack/data"),
            db_dir=Path("/tmp/state/custom-stack/db"),
            log_dir=Path("/tmp/state/custom-stack/logs"),
            compose_command=("docker", "compose"),
            compose_project="custom-stack",
            compose_files=(Path("/tmp/repo/docker-compose.yml"),),
            docker_context=Path("/tmp/repo"),
            registry_image="odoo-ai",
            healthcheck_url="https://custom-stack.example.com/web/health",
            update_modules=("AUTO",),
            services=("script-runner",),
            script_runner_service="script-runner",
            odoo_bin_path="/odoo/odoo-bin",
            image_variable_name="DOCKER_IMAGE",
            remote_host=None,
            remote_user=None,
            remote_port=None,
            remote_stack_path=None,
            remote_env_path=None,
            github_token=None,
        )
        stack_settings.env_file.parent.mkdir(parents=True, exist_ok=True)
        stack_settings.env_file.write_text("DOKPLOY_HOST=https://dokploy.example\n", encoding="utf-8")

        local_exec_commands: list[list[str]] = []

        with (
            patch.object(stack_data_workflow, "load_stack_settings", return_value=stack_settings),
            patch.object(stack_data_workflow, "build_updated_environment", return_value=stack_settings.environment.copy()),
            patch.object(stack_data_workflow, "ensure_local_bind_mounts"),
            patch.object(stack_data_workflow, "write_env_file"),
            patch.object(stack_data_workflow, "wait_for_local_service"),
            patch.object(stack_data_workflow, "_run_local_compose"),
            patch.object(stack_data_workflow, "_run_dokploy_managed_remote_data_workflow") as dokploy_runner,
            patch.object(stack_data_workflow, "local_compose_command", side_effect=lambda _settings, extra: ["docker", "compose", *extra]),
            patch.object(stack_data_workflow, "local_compose_env", return_value={}),
            patch.object(
                stack_data_workflow,
                "run_process",
                side_effect=lambda command, **_kwargs: local_exec_commands.append(list(command)),
            ),
        ):
            stack_data_workflow.run_stack_data_workflow("custom-stack", bootstrap=True)

        dokploy_runner.assert_not_called()
        self.assertTrue(local_exec_commands)

    def test_resolve_dokploy_remote_runtime_uses_compose_server_id_and_api_remote_config(self) -> None:
        deploy_servers = (
            {
                "serverId": "server-1",
                "name": "docker-cm-prod",
                "ipAddress": "100.73.170.113",
                "username": "root",
                "port": 22,
            },
            {
                "serverId": "server-2",
                "name": "docker-opw-prod",
                "ipAddress": "192.168.1.34",
                "username": "root",
                "port": 22,
            },
        )

        with (
            patch.object(stack_data_workflow, "collect_dokploy_deploy_servers", return_value=deploy_servers),
            patch.object(
                stack_data_workflow,
                "resolve_dokploy_compose_remote_config",
                return_value=(
                    Path("/etc/dokploy/applications/compose-input-haptic-protocol-hwmi8x"),
                    "compose-input-haptic-protocol-hwmi8x",
                ),
            ),
            patch.object(stack_data_workflow, "resolve_dokploy_compose_id", return_value=("compose-1", "opw-prod")),
            patch.object(stack_data_workflow, "dokploy_request", return_value={"serverId": "server-2"}),
        ):
            resolved = stack_data_workflow._resolve_dokploy_remote_runtime(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                compose_name="opw-prod",
                context_name="opw",
                instance_name="prod",
                env_values={},
            )

        self.assertEqual(
            resolved,
            (
                "docker-opw-prod",
                "root",
                22,
                Path("/etc/dokploy/applications/compose-input-haptic-protocol-hwmi8x"),
                "compose-input-haptic-protocol-hwmi8x",
            ),
        )

    def test_resolve_dokploy_remote_runtime_requires_explicit_host_when_server_linkage_is_missing(self) -> None:
        deploy_servers = (
            {
                "serverId": "server-1",
                "name": "docker-cm-prod",
                "ipAddress": "100.73.170.113",
                "username": "root",
                "port": 22,
            },
            {
                "serverId": "server-2",
                "name": "docker-opw-prod",
                "ipAddress": "192.168.1.34",
                "username": "root",
                "port": 22,
            },
        )

        with (
            patch.object(stack_data_workflow, "collect_dokploy_deploy_servers", return_value=deploy_servers),
            patch.object(
                stack_data_workflow,
                "resolve_dokploy_compose_remote_config",
                return_value=(Path("/etc/dokploy/applications/cm-testing"), "cm-testing"),
            ),
            patch.object(stack_data_workflow, "resolve_dokploy_compose_id", return_value=("compose-1", "cm-testing")),
            patch.object(stack_data_workflow, "dokploy_request", return_value={"serverId": None}),
        ):
            with self.assertRaises(ValueError) as raised_error:
                stack_data_workflow._resolve_dokploy_remote_runtime(
                    dokploy_host="https://dokploy.example",
                    dokploy_token="token",
                    compose_name="cm-testing",
                    context_name="cm",
                    instance_name="testing",
                    env_values={},
                )

        self.assertIn("Set DOKPLOY_SSH_HOST explicitly", str(raised_error.exception))

    def test_resolve_dokploy_remote_runtime_uses_override_host_with_override_path_and_project(self) -> None:
        deploy_servers = (
            {
                "name": "docker-cm-prod",
                "ipAddress": "100.73.170.113",
                "username": "root",
                "port": 22,
            },
            {
                "name": "docker-opw-prod",
                "ipAddress": "192.168.1.34",
                "username": "ubuntu",
                "port": 2222,
            },
        )

        with patch.object(stack_data_workflow, "collect_dokploy_deploy_servers", return_value=deploy_servers):
            resolved = stack_data_workflow._resolve_dokploy_remote_runtime(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                compose_name="opw-testing",
                context_name="opw",
                instance_name="testing",
                env_values={
                    "DOKPLOY_REMOTE_STACK_PATH_OPW_TESTING": "/etc/dokploy/applications/opw-testing",
                    "DOKPLOY_COMPOSE_PROJECT_OPW_TESTING": "opw-testing",
                    "DOKPLOY_SSH_HOST": "docker-opw-prod",
                },
            )

        self.assertEqual(
            resolved,
            (
                "docker-opw-prod",
                "ubuntu",
                2222,
                Path("/etc/dokploy/applications/opw-testing"),
                "opw-testing",
            ),
        )

    def test_resolve_dokploy_remote_runtime_allows_non_hyphenated_compose_name_with_overrides(self) -> None:
        deploy_servers = (
            {
                "serverId": "server-1",
                "name": "dokploy-host-1",
                "ipAddress": "10.0.0.1",
                "username": "root",
                "port": 22,
            },
        )

        with (
            patch.object(stack_data_workflow, "collect_dokploy_deploy_servers", return_value=deploy_servers),
            patch.object(stack_data_workflow, "resolve_dokploy_compose_id", return_value=("compose-1", "opsingle")),
            patch.object(stack_data_workflow, "dokploy_request", return_value={"serverId": "server-1"}),
        ):
            resolved = stack_data_workflow._resolve_dokploy_remote_runtime(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                compose_name="opsingle",
                context_name="opw",
                instance_name="prod",
                env_values={
                    "DOKPLOY_REMOTE_STACK_PATH_OPSINGLE": "/etc/dokploy/applications/opsingle",
                    "DOKPLOY_COMPOSE_PROJECT_OPSINGLE": "opsingle",
                },
            )

        self.assertEqual(
            resolved,
            (
                "dokploy-host-1",
                "root",
                22,
                Path("/etc/dokploy/applications/opsingle"),
                "opsingle",
            ),
        )


if __name__ == "__main__":
    unittest.main()
