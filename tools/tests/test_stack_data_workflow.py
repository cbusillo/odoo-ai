import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import click

from tools import stack_data_workflow
from tools.deployer.settings import StackSettings
from tools.platform.models import DokployTargetDefinition


def _sample_remote_stack_settings() -> StackSettings:
    return StackSettings(
        name="opw-testing",
        repo_root=Path("/tmp/repo"),
        env_file=Path("/tmp/opw-testing.env"),
        source_env_file=Path("/tmp/opw-testing.env"),
        environment={},
        state_root=Path("/tmp/state/opw-testing"),
        data_dir=Path("/tmp/state/opw-testing/data"),
        db_dir=Path("/tmp/state/opw-testing/db"),
        log_dir=Path("/tmp/state/opw-testing/logs"),
        compose_command=("docker", "compose"),
        compose_project="opw-testing",
        compose_files=(Path("/tmp/repo/docker-compose.yml"),),
        docker_context=Path("/tmp/repo"),
        registry_image="odoo-ai",
        healthcheck_url="https://opw-testing.example.com/web/health",
        update_modules=("AUTO",),
        services=("database", "script-runner", "web"),
        script_runner_service="script-runner",
        odoo_bin_path="/odoo/odoo-bin",
        image_variable_name="DOCKER_IMAGE",
        github_token=None,
    )


def _sample_remote_target_definition() -> DokployTargetDefinition:
    return DokployTargetDefinition(
        context="opw",
        instance="testing",
        target_id="compose-1",
        target_name="opw-testing",
        deploy_timeout_seconds=7200,
    )


class StackDataWorkflowTests(unittest.TestCase):
    def test_local_compose_command_writes_sanitized_compose_env_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            compose_env_file = repo_root / ".platform" / "env" / "opw.local.compose.env"
            compose_env_file.parent.mkdir(parents=True, exist_ok=True)
            stack_settings = StackSettings(
                name="opw-local",
                repo_root=repo_root,
                env_file=repo_root / ".platform" / "env" / "opw.local.env",
                source_env_file=repo_root / ".platform" / "env" / "opw.local.env",
                environment={
                    "DOCKER_IMAGE_REFERENCE": "odoo-ai@sha256:0123456789abcdef",
                    "DOCKER_IMAGE": "odoo-ai",
                    "ODOO_DB_PASSWORD": "database-password",
                },
                state_root=repo_root / ".platform" / "state" / "opw-local",
                data_dir=repo_root / ".platform" / "state" / "opw-local" / "data",
                db_dir=repo_root / ".platform" / "state" / "opw-local" / "db",
                log_dir=repo_root / ".platform" / "state" / "opw-local" / "logs",
                compose_command=("docker", "compose"),
                compose_project="odoo-opw-local",
                compose_files=(repo_root / "docker-compose.yml",),
                docker_context=repo_root,
                registry_image="odoo-ai",
                healthcheck_url="https://opw-local.example.com/web/health",
                update_modules=("AUTO",),
                services=("database", "web", "script-runner"),
                script_runner_service="script-runner",
                odoo_bin_path="/odoo/odoo-bin",
                image_variable_name="DOCKER_IMAGE",
                github_token=None,
            )

            command = stack_data_workflow.local_compose_command(stack_settings, ["build", "web"])
            compose_env_content = compose_env_file.read_text(encoding="utf-8")

        self.assertIn(str(compose_env_file), command)
        self.assertNotIn("DOCKER_IMAGE_REFERENCE=", compose_env_content)
        self.assertIn("DOCKER_IMAGE=odoo-ai", compose_env_content)
        self.assertIn(f"PLATFORM_RUNTIME_ENV_FILE={compose_env_file}", compose_env_content)

    def test_local_compose_uses_latest_written_env_file_values(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            env_file = repo_root / ".platform" / "env" / "opw.local.env"
            compose_env_file = env_file.with_suffix(".compose.env")
            env_file.parent.mkdir(parents=True, exist_ok=True)
            env_file.write_text(
                "\n".join(
                    (
                        "DOCKER_IMAGE=odoo-ai-updated",
                        "ODOO_DB_PASSWORD=database-password",
                        "DOCKER_IMAGE_REFERENCE=odoo-ai@sha256:0123456789abcdef",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            stack_settings = StackSettings(
                name="opw-local",
                repo_root=repo_root,
                env_file=env_file,
                source_env_file=env_file,
                environment={
                    "DOCKER_IMAGE": "odoo-ai-stale",
                    "ODOO_DB_PASSWORD": "database-password",
                    "DOCKER_IMAGE_REFERENCE": "odoo-ai@sha256:deadbeef",
                },
                state_root=repo_root / ".platform" / "state" / "opw-local",
                data_dir=repo_root / ".platform" / "state" / "opw-local" / "data",
                db_dir=repo_root / ".platform" / "state" / "opw-local" / "db",
                log_dir=repo_root / ".platform" / "state" / "opw-local" / "logs",
                compose_command=("docker", "compose"),
                compose_project="odoo-opw-local",
                compose_files=(repo_root / "docker-compose.yml",),
                docker_context=repo_root,
                registry_image="odoo-ai",
                healthcheck_url="https://opw-local.example.com/web/health",
                update_modules=("AUTO",),
                services=("database", "web", "script-runner"),
                script_runner_service="script-runner",
                odoo_bin_path="/odoo/odoo-bin",
                image_variable_name="DOCKER_IMAGE",
                github_token=None,
            )

            command = stack_data_workflow.local_compose_command(stack_settings, ["build", "web"])
            compose_environment = dict(stack_data_workflow.local_compose_env(stack_settings))
            compose_env_content = compose_env_file.read_text(encoding="utf-8")

        self.assertIn(str(compose_env_file), command)
        self.assertIn("DOCKER_IMAGE=odoo-ai-updated", compose_env_content)
        self.assertNotIn("DOCKER_IMAGE=odoo-ai-stale", compose_env_content)
        self.assertNotIn("DOCKER_IMAGE_REFERENCE=", compose_env_content)
        self.assertIn(f"PLATFORM_RUNTIME_ENV_FILE={compose_env_file}", compose_env_content)
        self.assertEqual(compose_environment.get("DOCKER_IMAGE"), "odoo-ai-updated")
        self.assertNotIn("DOCKER_IMAGE_REFERENCE", compose_environment)
        self.assertEqual(compose_environment.get("PLATFORM_RUNTIME_ENV_FILE"), str(compose_env_file))

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
            patch.object(stack_data_workflow, "_ensure_registry_auth_for_base_images"),
            patch.object(stack_data_workflow, "wait_for_local_service"),
            patch.object(stack_data_workflow, "_run_local_compose"),
            patch.object(stack_data_workflow, "_run_dokploy_managed_remote_data_workflow") as dokploy_runner,
            patch.object(
                stack_data_workflow, "local_compose_command", side_effect=lambda _settings, extra: ["docker", "compose", *extra]
            ),
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

    def test_local_data_workflow_builds_script_runner_before_execution(self) -> None:
        stack_settings = StackSettings(
            name="opw-local",
            repo_root=Path("/tmp/repo"),
            env_file=Path("/tmp/opw-local.env"),
            source_env_file=Path("/tmp/opw-local.env"),
            environment={
                "ODOO_DB_NAME": "opw",
                "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
                "ODOO_UPSTREAM_HOST": "source.example.com",
                "ODOO_UPSTREAM_USER": "root",
                "ODOO_UPSTREAM_DB_NAME": "opw",
                "ODOO_UPSTREAM_DB_USER": "odoo",
                "ODOO_UPSTREAM_FILESTORE_PATH": "/var/lib/odoo/filestore/opw",
            },
            state_root=Path("/tmp/state/opw-local"),
            data_dir=Path("/tmp/state/opw-local/data"),
            db_dir=Path("/tmp/state/opw-local/db"),
            log_dir=Path("/tmp/state/opw-local/logs"),
            compose_command=("docker", "compose"),
            compose_project="opw-local",
            compose_files=(Path("/tmp/repo/docker-compose.yml"),),
            docker_context=Path("/tmp/repo"),
            registry_image="odoo-ai",
            healthcheck_url="https://opw-local.example.com/web/health",
            update_modules=("AUTO",),
            services=("database", "script-runner", "web"),
            script_runner_service="script-runner",
            odoo_bin_path="/odoo/odoo-bin",
            image_variable_name="DOCKER_IMAGE",
            github_token=None,
        )
        compose_calls: list[list[str]] = []
        exec_commands: list[list[str]] = []
        stack_settings.env_file.write_text("ODOO_DB_USER=odoo\n", encoding="utf-8")

        def record_compose_call(_settings: StackSettings, extra: list[str], *, check: bool = True) -> None:
            self.assertIn(check, (True, False))
            compose_calls.append(list(extra))

        with (
            patch.object(stack_data_workflow, "load_stack_settings", return_value=stack_settings),
            patch.object(stack_data_workflow, "build_updated_environment", return_value=stack_settings.environment.copy()),
            patch.object(stack_data_workflow, "ensure_local_bind_mounts"),
            patch.object(stack_data_workflow, "write_env_file"),
            patch.object(stack_data_workflow, "_ensure_registry_auth_for_base_images") as ensure_registry_auth,
            patch.object(stack_data_workflow, "wait_for_local_service"),
            patch.object(stack_data_workflow, "_run_local_compose", side_effect=record_compose_call),
            patch.object(
                stack_data_workflow, "local_compose_command", side_effect=lambda _settings, extra: ["docker", "compose", *extra]
            ),
            patch.object(stack_data_workflow, "local_compose_env", return_value={}),
            patch.object(
                stack_data_workflow,
                "run_process",
                side_effect=lambda command, **_kwargs: exec_commands.append(list(command)),
            ),
        ):
            stack_data_workflow.run_stack_data_workflow("opw-local")

        self.assertGreaterEqual(len(compose_calls), 4)
        ensure_registry_auth.assert_called_once_with(stack_settings.environment)
        self.assertEqual(compose_calls[0], ["build", "web"])
        self.assertEqual(compose_calls[1], ["up", "-d", "--remove-orphans", "database"])
        self.assertEqual(compose_calls[2], ["up", "-d", "--remove-orphans", "script-runner"])
        self.assertEqual(compose_calls[3][:5], ["exec", "-T", "--user", "root", "script-runner"])
        self.assertEqual(compose_calls[4], ["stop", "web"])
        self.assertTrue(exec_commands)
        self.assertEqual(
            exec_commands[0],
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "-e",
                "ODOO_DB_NAME",
                "-e",
                "ODOO_FILESTORE_PATH",
                "-e",
                "ODOO_UPSTREAM_DB_NAME",
                "-e",
                "ODOO_UPSTREAM_DB_USER",
                "-e",
                "ODOO_UPSTREAM_FILESTORE_PATH",
                "-e",
                "ODOO_UPSTREAM_HOST",
                "-e",
                "ODOO_UPSTREAM_USER",
                "script-runner",
                "python3",
                "-u",
                stack_data_workflow.DATA_WORKFLOW_SCRIPT,
            ],
        )

    def test_local_update_only_workflow_skips_upstream_requirements_and_passes_flag(self) -> None:
        stack_settings = StackSettings(
            name="opw-local",
            repo_root=Path("/tmp/repo"),
            env_file=Path("/tmp/opw-local.env"),
            source_env_file=Path("/tmp/opw-local.env"),
            environment={
                "ODOO_DB_NAME": "opw",
                "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
            },
            state_root=Path("/tmp/state/opw-local"),
            data_dir=Path("/tmp/state/opw-local/data"),
            db_dir=Path("/tmp/state/opw-local/db"),
            log_dir=Path("/tmp/state/opw-local/logs"),
            compose_command=("docker", "compose"),
            compose_project="opw-local",
            compose_files=(Path("/tmp/repo/docker-compose.yml"),),
            docker_context=Path("/tmp/repo"),
            registry_image="odoo-ai",
            healthcheck_url="https://opw-local.example.com/web/health",
            update_modules=("AUTO",),
            services=("database", "script-runner", "web"),
            script_runner_service="script-runner",
            odoo_bin_path="/odoo/odoo-bin",
            image_variable_name="DOCKER_IMAGE",
            github_token=None,
        )
        exec_commands: list[list[str]] = []
        stack_settings.env_file.write_text("ODOO_DB_USER=odoo\n", encoding="utf-8")

        with (
            patch.object(stack_data_workflow, "load_stack_settings", return_value=stack_settings),
            patch.object(stack_data_workflow, "build_updated_environment", return_value=stack_settings.environment.copy()),
            patch.object(stack_data_workflow, "ensure_local_bind_mounts"),
            patch.object(stack_data_workflow, "write_env_file"),
            patch.object(stack_data_workflow, "_ensure_registry_auth_for_base_images"),
            patch.object(stack_data_workflow, "wait_for_local_service"),
            patch.object(stack_data_workflow, "_run_local_compose"),
            patch.object(
                stack_data_workflow, "local_compose_command", side_effect=lambda _settings, extra: ["docker", "compose", *extra]
            ),
            patch.object(stack_data_workflow, "local_compose_env", return_value={}),
            patch.object(
                stack_data_workflow,
                "run_process",
                side_effect=lambda command, **_kwargs: exec_commands.append(list(command)),
            ),
        ):
            stack_data_workflow.run_stack_data_workflow("opw-local", update_only=True)

        self.assertTrue(exec_commands)
        self.assertEqual(exec_commands[0][-1], "--update-only")

    def test_local_data_workflow_fails_before_compose_build_when_base_images_are_unset(self) -> None:
        stack_settings = StackSettings(
            name="opw-local",
            repo_root=Path("/tmp/repo"),
            env_file=Path("/tmp/opw-local.env"),
            source_env_file=Path("/tmp/opw-local.env"),
            environment={
                "ODOO_DB_NAME": "opw",
                "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
                "ODOO_UPSTREAM_HOST": "source.example.com",
                "ODOO_UPSTREAM_USER": "root",
                "ODOO_UPSTREAM_DB_NAME": "opw",
                "ODOO_UPSTREAM_DB_USER": "odoo",
                "ODOO_UPSTREAM_FILESTORE_PATH": "/var/lib/odoo/filestore/opw",
            },
            state_root=Path("/tmp/state/opw-local"),
            data_dir=Path("/tmp/state/opw-local/data"),
            db_dir=Path("/tmp/state/opw-local/db"),
            log_dir=Path("/tmp/state/opw-local/logs"),
            compose_command=("docker", "compose"),
            compose_project="opw-local",
            compose_files=(Path("/tmp/repo/docker-compose.yml"),),
            docker_context=Path("/tmp/repo"),
            registry_image="odoo-ai",
            healthcheck_url="https://opw-local.example.com/web/health",
            update_modules=("AUTO",),
            services=("database", "script-runner", "web"),
            script_runner_service="script-runner",
            odoo_bin_path="/odoo/odoo-bin",
            image_variable_name="DOCKER_IMAGE",
            github_token=None,
        )
        stack_settings.env_file.write_text("ODOO_DB_USER=odoo\n", encoding="utf-8")

        with (
            patch.object(stack_data_workflow, "load_stack_settings", return_value=stack_settings),
            patch.object(stack_data_workflow, "build_updated_environment", return_value=stack_settings.environment.copy()),
            patch.object(stack_data_workflow, "ensure_local_bind_mounts"),
            patch.object(stack_data_workflow, "write_env_file"),
            patch.object(
                stack_data_workflow,
                "_ensure_registry_auth_for_base_images",
                side_effect=click.ClickException("ODOO_BASE_RUNTIME_IMAGE must be set"),
            ),
            patch.object(stack_data_workflow, "_run_local_compose") as run_local_compose,
        ):
            with self.assertRaises(click.ClickException) as captured_error:
                stack_data_workflow.run_stack_data_workflow("opw-local")

        self.assertIn("ODOO_BASE_RUNTIME_IMAGE", captured_error.exception.message)
        run_local_compose.assert_not_called()

    def test_resolve_dokploy_schedule_runtime_uses_server_schedule_for_linked_server(self) -> None:
        with patch.object(
            stack_data_workflow,
            "dokploy_request",
            return_value={"serverId": "server-2", "appName": "compose-opw-prod-abc123"},
        ):
            resolved = stack_data_workflow._resolve_dokploy_schedule_runtime(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                compose_id="compose-1",
                compose_name="opw-prod",
            )

        self.assertEqual(resolved, ("server", "server-2", "compose-opw-prod-abc123", "server-2"))

    def test_resolve_dokploy_schedule_runtime_uses_dokploy_server_when_server_linkage_is_missing(self) -> None:
        with (
            patch.object(
                stack_data_workflow,
                "dokploy_request",
                return_value={"serverId": None, "appName": "compose-cm-testing-abc123"},
            ),
            patch.object(stack_data_workflow, "resolve_dokploy_user_id", return_value="user-123"),
        ):
            resolved = stack_data_workflow._resolve_dokploy_schedule_runtime(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                compose_id="compose-1",
                compose_name="cm-testing",
            )

        self.assertEqual(resolved, ("dokploy-server", "user-123", "compose-cm-testing-abc123", None))

    def test_build_dokploy_data_workflow_script_includes_project_labels_and_flags(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            bootstrap=True,
            no_sanitize=True,
            update_only=False,
            clear_stale_lock=True,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertIn("com.docker.compose.project=${compose_project}", schedule_script)
        self.assertIn('script_runner_container_id=$(resolve_container_id "script-runner")', schedule_script)
        self.assertIn("--bootstrap", schedule_script)
        self.assertIn("--no-sanitize", schedule_script)
        self.assertIn("Clearing stale data workflow lock ${data_workflow_lock_path}", schedule_script)
        self.assertIn("docker exec -u root", schedule_script)
        self.assertIn("Normalizing filestore ownership for ${database_name}", schedule_script)
        self.assertIn("workflow_ssh_dir=/tmp/platform-data-workflow-ssh", schedule_script)
        self.assertIn('workflow_identity_key=""', schedule_script)
        self.assertIn('workflow_identity_key="$WORKFLOW_SSH_DIR/$(basename "$source_key_path")"', schedule_script)
        self.assertIn("for candidate_key in id_ed25519 id_ecdsa id_rsa id_dsa; do", schedule_script)
        self.assertIn('install -m 600 -o "$WORKFLOW_UID" -g "$WORKFLOW_GID"', schedule_script)

    def test_build_dokploy_data_workflow_script_runs_main_workflow_non_root(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            bootstrap=True,
            no_sanitize=False,
            update_only=False,
            clear_stale_lock=True,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertIn('docker exec -u root "${script_runner_container_id}" rm -f', schedule_script)
        self.assertIn('docker exec "${script_runner_container_id}"', schedule_script)
        self.assertIn('-e DATA_WORKFLOW_SSH_DIR="${workflow_ssh_dir}"', schedule_script)
        self.assertIn('-e DATA_WORKFLOW_SSH_KEY="$workflow_identity_key"', schedule_script)
        self.assertIn("python3 -u /volumes/scripts/run_odoo_data_workflows.py", schedule_script)
        self.assertNotIn("${workflow_ssh_dir}/id_rsa", schedule_script)
        self.assertNotIn('docker exec -u root "${script_runner_container_id}"     python3 -u', schedule_script)

    def test_build_dokploy_data_workflow_script_limits_root_usage_to_lock_cleanup(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            bootstrap=False,
            no_sanitize=False,
            update_only=False,
            clear_stale_lock=True,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertEqual(schedule_script.count("docker exec -u root"), 2)

    def test_build_dokploy_data_workflow_script_uses_one_root_exec_without_lock_cleanup(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            bootstrap=False,
            no_sanitize=False,
            update_only=False,
            clear_stale_lock=False,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertIn("clear_stale_lock=0", schedule_script)
        self.assertEqual(schedule_script.count("docker exec -u root"), 2)

    def test_build_dokploy_data_workflow_script_normalizes_blank_filestore_path(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            filestore_path="   ",
            bootstrap=False,
            no_sanitize=False,
            update_only=False,
            clear_stale_lock=False,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertIn("filestore_root=/volumes/data/filestore", schedule_script)

    def test_build_dokploy_data_workflow_script_includes_update_only_flag(self) -> None:
        schedule_script = stack_data_workflow._build_dokploy_data_workflow_script(
            compose_app_name="compose-opw-testing-abc123",
            database_name="opw",
            bootstrap=False,
            no_sanitize=False,
            update_only=True,
            clear_stale_lock=False,
            data_workflow_lock_path="/volumes/data/.data_workflow_in_progress",
        )

        self.assertIn("--update-only", schedule_script)

    @staticmethod
    def test_sync_dokploy_target_environment_and_deploy_skips_compose_deploy_when_env_matches() -> None:
        target_definition = _sample_remote_target_definition()

        with (
            patch.object(
                stack_data_workflow,
                "fetch_dokploy_target_payload",
                return_value={"env": "ODOO_DB_NAME=opw\nODOO_FILESTORE_PATH=/volumes/data/filestore"},
            ),
            patch.object(stack_data_workflow, "update_dokploy_target_env") as update_target_env,
            patch.object(stack_data_workflow, "latest_deployment_for_compose") as latest_deployment,
            patch.object(stack_data_workflow, "wait_for_dokploy_compose_deployment") as wait_for_compose,
            patch.object(stack_data_workflow, "dokploy_request") as dokploy_request,
        ):
            stack_data_workflow._sync_dokploy_target_environment_and_deploy(
                dokploy_host="https://dokploy.example",
                dokploy_token="token",
                target_definition=target_definition,
                env_values={
                    "ODOO_DB_NAME": "opw",
                    "ODOO_FILESTORE_PATH": "/volumes/data/filestore",
                },
                deploy_timeout_seconds=7200,
            )

        update_target_env.assert_not_called()
        latest_deployment.assert_not_called()
        wait_for_compose.assert_not_called()
        dokploy_request.assert_not_called()

    def test_run_dokploy_managed_remote_data_workflow_normalizes_blank_filestore_path(self) -> None:
        stack_settings = _sample_remote_stack_settings()
        target_definition = _sample_remote_target_definition()

        with (
            patch.object(
                stack_data_workflow,
                "_resolve_required_dokploy_compose_target_definition",
                return_value=target_definition,
            ),
            patch.object(
                stack_data_workflow,
                "_resolve_dokploy_schedule_runtime",
                return_value=("dokploy-server", "user-123", "compose-opw-testing-abc123", None),
            ),
            patch.object(stack_data_workflow, "find_matching_dokploy_schedule", return_value=None),
            patch.object(stack_data_workflow, "_sync_dokploy_target_environment_and_deploy"),
            patch.object(
                stack_data_workflow, "upsert_dokploy_schedule", return_value={"scheduleId": "schedule-123"}
            ) as upsert_schedule,
            patch.object(
                stack_data_workflow,
                "latest_deployment_for_schedule",
                side_effect=[{"deploymentId": "before-1", "status": "done"}, {"deploymentId": "after-1", "status": "done"}],
            ),
            patch.object(
                stack_data_workflow,
                "wait_for_dokploy_schedule_deployment",
                return_value="deployment=after-1 status=done",
            ) as wait_for_schedule,
            patch.object(stack_data_workflow, "dokploy_request", return_value=True),
        ):
            exit_code = stack_data_workflow._run_dokploy_managed_remote_data_workflow(
                stack_settings,
                {
                    "DOKPLOY_HOST": "https://dokploy.example",
                    "DOKPLOY_TOKEN": "token",
                    "ODOO_DB_NAME": "opw",
                    "ODOO_FILESTORE_PATH": "   ",
                },
                bootstrap=False,
                no_sanitize=False,
                update_only=False,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(wait_for_schedule.call_args.kwargs["timeout_seconds"], 7200)
        upsert_payload = upsert_schedule.call_args.kwargs["schedule_payload"]
        self.assertIn("filestore_root=/volumes/data/filestore", str(upsert_payload["script"]))

    def test_should_clear_stale_data_workflow_lock_only_for_cancelled_latest_deployment(self) -> None:
        self.assertTrue(
            stack_data_workflow._should_clear_stale_data_workflow_lock(
                {
                    "deployments": [
                        {"status": "cancelled"},
                    ]
                }
            )
        )
        self.assertFalse(
            stack_data_workflow._should_clear_stale_data_workflow_lock(
                {
                    "deployments": [
                        {"status": "running"},
                        {"status": "cancelled"},
                    ]
                }
            )
        )
        self.assertFalse(
            stack_data_workflow._should_clear_stale_data_workflow_lock(
                {
                    "deployments": [
                        {"status": "done"},
                    ]
                }
            )
        )
        self.assertTrue(
            stack_data_workflow._should_clear_stale_data_workflow_lock(
                {
                    "deployments": [
                        {"status": "error"},
                        {"status": "cancelled"},
                        {"status": "error"},
                    ]
                }
            )
        )

    def test_run_dokploy_managed_remote_data_workflow_upserts_and_runs_schedule(self) -> None:
        stack_settings = _sample_remote_stack_settings()
        target_definition = _sample_remote_target_definition()
        dokploy_request_calls: list[dict[str, object]] = []
        updated_target_env_calls: list[dict[str, object]] = []

        def record_dokploy_request(**kwargs: object) -> object:
            dokploy_request_calls.append(dict(kwargs))
            return True

        def record_target_env_update(**kwargs: object) -> None:
            updated_target_env_calls.append(dict(kwargs))

        with (
            patch.object(
                stack_data_workflow,
                "_resolve_required_dokploy_compose_target_definition",
                return_value=target_definition,
            ),
            patch.object(
                stack_data_workflow,
                "_resolve_dokploy_schedule_runtime",
                return_value=("dokploy-server", "user-123", "compose-opw-testing-abc123", None),
            ),
            patch.object(
                stack_data_workflow,
                "find_matching_dokploy_schedule",
                return_value={"deployments": [{"status": "cancelled"}]},
            ),
            patch.object(
                stack_data_workflow,
                "fetch_dokploy_target_payload",
                return_value={
                    "env": "ODOO_ADDON_REPOSITORIES=cbusillo/disable_odoo_online@main,OCA/OpenUpgrade@19.0\n"
                    "OPENUPGRADE_ADDON_REPOSITORY=OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417\n"
                    "OPENUPGRADELIB_INSTALL_SPEC=git+https://github.com/OCA/openupgradelib.git@46d66ff5ed6a99481f84d3c79fc6e50835da7286",
                },
            ),
            patch.object(stack_data_workflow, "update_dokploy_target_env", side_effect=record_target_env_update),
            patch.object(
                stack_data_workflow,
                "upsert_dokploy_schedule",
                return_value={"scheduleId": "schedule-123"},
            ) as upsert_schedule,
            patch.object(
                stack_data_workflow,
                "latest_deployment_for_compose",
                return_value={"deploymentId": "compose-before-1", "status": "done"},
            ),
            patch.object(
                stack_data_workflow,
                "wait_for_dokploy_compose_deployment",
                return_value="deployment=compose-after-1 status=done",
            ),
            patch.object(
                stack_data_workflow,
                "latest_deployment_for_schedule",
                side_effect=[{"deploymentId": "before-1", "status": "done"}, {"deploymentId": "after-1", "status": "done"}],
            ),
            patch.object(stack_data_workflow, "wait_for_dokploy_schedule_deployment", return_value="deployment=after-1 status=done"),
            patch.object(stack_data_workflow, "dokploy_request", side_effect=record_dokploy_request),
        ):
            exit_code = stack_data_workflow._run_dokploy_managed_remote_data_workflow(
                stack_settings,
                {
                    "DOKPLOY_HOST": "https://dokploy.example",
                    "DOKPLOY_TOKEN": "token",
                    "ODOO_DB_NAME": "opw",
                    "ODOO_ADDON_REPOSITORIES": "cbusillo/disable_odoo_online@main,"
                    "OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
                    "OPENUPGRADE_ADDON_REPOSITORY": "OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
                    "OPENUPGRADELIB_INSTALL_SPEC": "git+https://github.com/OCA/openupgradelib.git@"
                    "46d66ff5ed6a99481f84d3c79fc6e50835da7286",
                },
                bootstrap=True,
                no_sanitize=True,
                update_only=False,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(updated_target_env_calls), 1)
        rendered_env_text = str(updated_target_env_calls[0]["env_text"])
        self.assertIn(
            "ODOO_ADDON_REPOSITORIES=cbusillo/disable_odoo_online@main,OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
            rendered_env_text,
        )
        upsert_payload = upsert_schedule.call_args.kwargs["schedule_payload"]
        self.assertEqual(upsert_payload["scheduleType"], "dokploy-server")
        self.assertEqual(upsert_payload["userId"], "user-123")
        self.assertEqual(upsert_payload["enabled"], False)
        self.assertEqual(upsert_payload["timezone"], "UTC")
        self.assertIn("Clearing stale data workflow lock ${data_workflow_lock_path}", str(upsert_payload["script"]))
        self.assertIn("Normalizing filestore ownership for ${database_name}", str(upsert_payload["script"]))
        self.assertIn("--bootstrap", str(upsert_payload["script"]))
        self.assertIn("--no-sanitize", str(upsert_payload["script"]))
        self.assertEqual(
            dokploy_request_calls,
            [
                {
                    "host": "https://dokploy.example",
                    "token": "token",
                    "path": "/api/compose.deploy",
                    "method": "POST",
                    "payload": {"composeId": "compose-1"},
                    "timeout_seconds": 7200,
                },
                {
                    "host": "https://dokploy.example",
                    "token": "token",
                    "path": "/api/schedule.runManually",
                    "method": "POST",
                    "payload": {"scheduleId": "schedule-123"},
                    "timeout_seconds": 7200,
                },
            ],
        )

    def test_run_dokploy_managed_remote_data_workflow_requires_database_name(self) -> None:
        stack_settings = _sample_remote_stack_settings()
        target_definition = _sample_remote_target_definition()

        with (
            patch.object(
                stack_data_workflow,
                "_resolve_required_dokploy_compose_target_definition",
                return_value=target_definition,
            ),
            patch.object(
                stack_data_workflow,
                "_resolve_dokploy_schedule_runtime",
                return_value=("dokploy-server", "user-123", "compose-opw-testing-abc123", None),
            ),
            patch.object(stack_data_workflow, "_sync_dokploy_target_environment_and_deploy") as sync_target,
            patch.object(stack_data_workflow, "find_matching_dokploy_schedule", return_value=None),
        ):
            with self.assertRaisesRegex(ValueError, "requires ODOO_DB_NAME"):
                stack_data_workflow._run_dokploy_managed_remote_data_workflow(
                    stack_settings,
                    {
                        "DOKPLOY_HOST": "https://dokploy.example",
                        "DOKPLOY_TOKEN": "token",
                    },
                    bootstrap=False,
                    no_sanitize=False,
                    update_only=False,
                )
        sync_target.assert_not_called()


if __name__ == "__main__":
    unittest.main()
