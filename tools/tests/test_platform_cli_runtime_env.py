import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import click

from tools.platform.cli import (
    _assert_prod_data_workflow_allowed,
    _assert_promote_path_allowed,
    _build_runtime_env_values,
    _collect_dirty_tracked_files,
    _collect_environment_gate_results,
    _compose_base_command,
    _dokploy_request,
    _load_environment,
    _resolve_ship_health_timeout_seconds,
    _resolve_ship_healthcheck_urls,
    _resolve_ship_timeout_seconds,
    _run_code_gate,
    _run_production_backup_gate,
    _run_with_web_temporarily_stopped,
    _validate_target_gate_policy,
)
from tools.platform.models import (
    ContextDefinition,
    DokployTargetDefinition,
    InstanceDefinition,
    RuntimeSelection,
    StackDefinition,
)
from tools.tests.platform_test_helpers import write_compose_stack_files, write_runtime_env_file


def _sample_runtime_selection() -> RuntimeSelection:
    context_definition = ContextDefinition()
    instance_definition = InstanceDefinition()
    return RuntimeSelection(
        context_name="opw",
        instance_name="local",
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name="opw",
        project_name="odoo-opw-local",
        state_path=Path("/tmp/opw-state"),
        data_mount=Path("/tmp/opw-data"),
        runtime_conf_host_path=Path("/tmp/opw-state/platform.odoo.conf"),
        data_volume_name="odoo-opw-local-data",
        log_volume_name="odoo-opw-local-logs",
        db_volume_name="odoo-opw-local-db",
        web_host_port=8069,
        longpoll_host_port=8072,
        db_host_port=15432,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=("opw_custom",),
        effective_addon_repositories=("cbusillo/disable_odoo_online@main",),
        effective_runtime_env={},
    )


def _sample_stack_definition() -> StackDefinition:
    return StackDefinition(
        schema_version=1,
        odoo_version="19.0",
        addons_path=("/odoo/addons",),
        contexts={"opw": ContextDefinition()},
    )


class PlatformRuntimeEnvironmentTests(unittest.TestCase):
    @staticmethod
    def _build_runtime_values(
        *,
        runtime_env_file: str,
        runtime_selection: RuntimeSelection | None = None,
        source_environment: dict[str, str] | None = None,
    ) -> dict[str, str]:
        return _build_runtime_env_values(
            runtime_env_file=Path(runtime_env_file),
            stack_definition=_sample_stack_definition(),
            runtime_selection=runtime_selection or _sample_runtime_selection(),
            source_environment=source_environment or {
                "ODOO_DB_USER": "odoo",
                "ODOO_DB_PASSWORD": "database-password",
            },
        )

    def test_compose_base_command_uses_expected_layer_order(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            write_compose_stack_files(repo_root)
            runtime_env_file = write_runtime_env_file(repo_root)

            with patch("tools.platform.cli._discover_repo_root", return_value=repo_root):
                command = _compose_base_command(runtime_env_file)

        self.assertEqual(command[:6], ["docker", "compose", "--project-directory", str(repo_root), "--env-file", str(runtime_env_file)])
        self.assertEqual(
            command[6:],
            [
                "-f",
                str(repo_root / "docker-compose.yml"),
                "-f",
                str(repo_root / "platform" / "compose" / "base.yaml"),
                "-f",
                str(repo_root / "docker-compose.override.yml"),
            ],
        )

    def test_compose_base_command_allows_missing_override_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            write_compose_stack_files(repo_root, include_override=False)
            runtime_env_file = write_runtime_env_file(repo_root)

            with patch("tools.platform.cli._discover_repo_root", return_value=repo_root):
                command = _compose_base_command(runtime_env_file)

        self.assertNotIn(str(repo_root / "docker-compose.override.yml"), command)

    def test_collect_dirty_tracked_files_filters_blank_lines(self) -> None:
        with patch(
            "tools.platform.cli._run_command_capture",
            return_value=" M platform/dokploy.toml\n\nM tools/platform/cli.py\n",
        ):
            dirty_lines = _collect_dirty_tracked_files()

        self.assertEqual(dirty_lines, ("M platform/dokploy.toml", "M tools/platform/cli.py"))

    def test_runtime_env_includes_admin_credential_keys_when_configured(self) -> None:
        runtime_values = _build_runtime_env_values(
            runtime_env_file=Path("/tmp/opw.local.env"),
            stack_definition=_sample_stack_definition(),
            runtime_selection=_sample_runtime_selection(),
            source_environment={
                "ODOO_DB_USER": "odoo",
                "ODOO_DB_PASSWORD": "database-password",
                "ODOO_MASTER_PASSWORD": "master-password",
                "ODOO_ADMIN_LOGIN": "admin",
                "ODOO_ADMIN_PASSWORD": "secure-password",
                "ODOO_KEY": "key-from-source",
                "ODOO_UPSTREAM_HOST": "opw-prod.shiny",
                "ODOO_UPSTREAM_DB_NAME": "opw",
                "ODOO_UPSTREAM_DB_USER": "odoo",
                "ODOO_UPSTREAM_FILESTORE_PATH": "/opt/odoo/local_data/filestore",
                "DATA_WORKFLOW_SSH_KEY": "/root/.ssh/id_rsa",
                "ODOO_DATA_WORKFLOW_LOCK_FILE": "/volumes/data/.data_workflow_in_progress",
                "ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS": "7200",
            },
        )

        self.assertEqual(runtime_values.get("ODOO_ADMIN_LOGIN"), "admin")
        self.assertEqual(runtime_values.get("ODOO_ADMIN_PASSWORD"), "secure-password")
        self.assertEqual(runtime_values.get("ODOO_KEY"), "key-from-source")
        self.assertEqual(runtime_values.get("ODOO_UPSTREAM_HOST"), "opw-prod.shiny")
        self.assertEqual(runtime_values.get("DATA_WORKFLOW_SSH_KEY"), "/root/.ssh/id_rsa")
        self.assertEqual(
            runtime_values.get("ODOO_DATA_WORKFLOW_LOCK_FILE"),
            "/volumes/data/.data_workflow_in_progress",
        )

    def test_runtime_env_sets_restore_defaults(self) -> None:
        runtime_values = self._build_runtime_values(runtime_env_file="/tmp/cm.local.env")

        self.assertEqual(runtime_values.get("ODOO_FILESTORE_PATH"), "/volumes/data/filestore")
        self.assertEqual(
            runtime_values.get("ODOO_DATA_WORKFLOW_LOCK_FILE"),
            "/volumes/data/.data_workflow_in_progress",
        )
        self.assertEqual(runtime_values.get("ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS"), "7200")

    def test_runtime_env_adds_openupgrade_repo_when_enabled(self) -> None:
        runtime_values = self._build_runtime_values(
            runtime_env_file="/tmp/opw.local.env",
            source_environment={
                "ODOO_DB_USER": "odoo",
                "ODOO_DB_PASSWORD": "database-password",
                "OPENUPGRADE_ENABLED": "True",
            },
        )

        self.assertEqual(
            runtime_values.get("ODOO_ADDON_REPOSITORIES"),
            "cbusillo/disable_odoo_online@main,OCA/OpenUpgrade@19.0",
        )
        self.assertEqual(
            runtime_values.get("ODOO_PYTHON_SYNC_SKIP_ADDONS"),
            "openupgrade_framework,openupgrade_scripts,openupgrade_scripts_custom",
        )

    def test_runtime_env_does_not_duplicate_openupgrade_repo(self) -> None:
        runtime_selection = replace(
            _sample_runtime_selection(),
            effective_addon_repositories=(
                "cbusillo/disable_odoo_online@main",
                "OCA/OpenUpgrade@19.0",
            ),
        )

        runtime_values = self._build_runtime_values(
            runtime_env_file="/tmp/opw.local.env",
            runtime_selection=runtime_selection,
            source_environment={
                "ODOO_DB_USER": "odoo",
                "ODOO_DB_PASSWORD": "database-password",
                "OPENUPGRADE_ENABLED": "True",
            },
        )

        self.assertEqual(
            runtime_values.get("ODOO_ADDON_REPOSITORIES"),
            "cbusillo/disable_odoo_online@main,OCA/OpenUpgrade@19.0",
        )

    def test_runtime_env_keeps_python_sync_skip_addons_empty_without_openupgrade(self) -> None:
        runtime_values = self._build_runtime_values(runtime_env_file="/tmp/opw.local.env")

        self.assertEqual(runtime_values.get("ODOO_PYTHON_SYNC_SKIP_ADDONS"), "")

    def test_load_environment_scopes_admin_keys_by_context(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            temporary_directory = Path(temporary_directory_name)
            (temporary_directory / ".env").write_text("ODOO_DB_USER=odoo\n", encoding="utf-8")

            platform_directory = temporary_directory / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    [
                        "schema_version = 1",
                        "",
                        "[contexts.cm.shared]",
                        'ODOO_ADMIN_LOGIN = "admin"',
                        'ODOO_ADMIN_PASSWORD = "secure-password"',
                        "",
                        "[contexts.opw.shared]",
                        'ENV_OVERRIDE_SHOPIFY__TEST_STORE = true',
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            _env_file_path, cm_environment = _load_environment(
                temporary_directory,
                None,
                context_name="cm",
                instance_name="local",
            )
            _env_file_path, opw_environment = _load_environment(
                temporary_directory,
                None,
                context_name="opw",
                instance_name="local",
            )

            self.assertEqual(cm_environment.get("ODOO_ADMIN_LOGIN"), "admin")
            self.assertEqual(cm_environment.get("ODOO_ADMIN_PASSWORD"), "secure-password")
            self.assertIsNone(opw_environment.get("ODOO_ADMIN_LOGIN"))
            self.assertIsNone(opw_environment.get("ODOO_ADMIN_PASSWORD"))


class PlatformWebPauseTests(unittest.TestCase):
    def test_web_pause_wraps_operation_and_restarts(self) -> None:
        executed_commands: list[list[str]] = []

        def operation() -> None:
            executed_commands.append(["operation"])

        with (
            patch("tools.platform.cli._compose_base_command", return_value=["docker", "compose"]),
            patch(
                "tools.platform.cli._run_command_best_effort",
                side_effect=lambda command: executed_commands.append(command) or 0,
            ),
        ):
            _run_with_web_temporarily_stopped(
                Path("/tmp/runtime.env"),
                operation,
                dry_run=False,
                dry_run_commands=(),
            )

        self.assertEqual(executed_commands[0], ["docker", "compose", "stop", "web"])
        self.assertEqual(executed_commands[1], ["operation"])
        self.assertEqual(executed_commands[2], ["docker", "compose", "up", "-d", "web"])

    def test_web_pause_restarts_even_when_operation_fails(self) -> None:
        executed_commands: list[list[str]] = []

        def operation() -> None:
            executed_commands.append(["operation"])
            raise RuntimeError("boom")

        with (
            patch("tools.platform.cli._compose_base_command", return_value=["docker", "compose"]),
            patch(
                "tools.platform.cli._run_command_best_effort",
                side_effect=lambda command: executed_commands.append(command) or 0,
            ),
        ):
            with self.assertRaises(RuntimeError):
                _run_with_web_temporarily_stopped(
                    Path("/tmp/runtime.env"),
                    operation,
                    dry_run=False,
                    dry_run_commands=(),
                )

        self.assertEqual(executed_commands[0], ["docker", "compose", "stop", "web"])
        self.assertEqual(executed_commands[1], ["operation"])
        self.assertEqual(executed_commands[2], ["docker", "compose", "up", "-d", "web"])


class PlatformShipHealthcheckResolutionTests(unittest.TestCase):
    def test_ship_timeout_prefers_target_override(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            deploy_timeout_seconds=1800,
        )

        resolved_timeout_seconds = _resolve_ship_timeout_seconds(
            timeout_override_seconds=None,
            target_definition=target_definition,
        )

        self.assertEqual(resolved_timeout_seconds, 1800)

    def test_ship_health_timeout_prefers_target_override(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            healthcheck_timeout_seconds=420,
        )

        resolved_timeout_seconds = _resolve_ship_health_timeout_seconds(
            health_timeout_override_seconds=None,
            target_definition=target_definition,
        )

        self.assertEqual(resolved_timeout_seconds, 420)

    def test_healthcheck_urls_resolve_from_target_domains(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            domains=("cm-testing.shinycomputers.com",),
        )

        healthcheck_urls = _resolve_ship_healthcheck_urls(
            target_definition=target_definition,
            environment_values={},
        )

        self.assertEqual(healthcheck_urls, ("https://cm-testing.shinycomputers.com/web/health",))

    def test_healthcheck_urls_fallback_to_base_url_env(self) -> None:
        healthcheck_urls = _resolve_ship_healthcheck_urls(
            target_definition=None,
            environment_values={
                "ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL": "https://cm-dev.shinycomputers.com",
            },
        )

        self.assertEqual(healthcheck_urls, ("https://cm-dev.shinycomputers.com/web/health",))

    def test_healthcheck_urls_respect_disabled_flag(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            domains=("cm-testing.shinycomputers.com",),
            healthcheck_enabled=False,
        )

        healthcheck_urls = _resolve_ship_healthcheck_urls(
            target_definition=target_definition,
            environment_values={},
        )

        self.assertEqual(healthcheck_urls, ())


class PlatformGateHelpersTests(unittest.TestCase):
    def test_prod_data_workflow_blocked_without_break_glass(self) -> None:
        with self.assertRaises(click.ClickException):
            _assert_prod_data_workflow_allowed(
                instance_name="prod",
                workflow="restore",
                allow_prod_data_workflow=False,
            )

    @staticmethod
    def test_prod_data_workflow_allowed_with_break_glass() -> None:
        _assert_prod_data_workflow_allowed(
            instance_name="prod",
            workflow="restore",
            allow_prod_data_workflow=True,
        )

    def test_environment_gate_collects_health_results(self) -> None:
        with patch("tools.platform.cli._wait_for_ship_healthcheck", return_value="http 200 status=pass"):
            results = _collect_environment_gate_results(
                urls=("https://cm-testing.shinycomputers.com/web/health",),
                timeout_seconds=30,
            )

        self.assertEqual(
            results,
            [{"url": "https://cm-testing.shinycomputers.com/web/health", "result": "http 200 status=pass"}],
        )

    def test_environment_gate_requires_healthcheck_urls(self) -> None:
        with self.assertRaises(click.ClickException):
            _collect_environment_gate_results(urls=(), timeout_seconds=30)

    @staticmethod
    def test_promote_path_allows_testing_to_prod_only() -> None:
        _assert_promote_path_allowed(
            from_instance_name="testing",
            to_instance_name="prod",
        )

    def test_promote_path_blocks_non_release_path(self) -> None:
        with self.assertRaises(click.ClickException):
            _assert_promote_path_allowed(
                from_instance_name="dev",
                to_instance_name="testing",
            )

    @staticmethod
    def test_production_backup_gate_invokes_expected_command() -> None:
        with patch("tools.platform.cli._run_gate_command") as run_gate_command_mock:
            _run_production_backup_gate(context_name="cm", dry_run=False)

        run_gate_command_mock.assert_called_once_with(
            ["uv", "run", "prod-gate", "backup", "--target", "cm"],
            dry_run=False,
        )

    @staticmethod
    def test_code_gate_uses_gate_profile() -> None:
        with patch("tools.platform.cli._run_gate_command") as run_gate_command_mock:
            _run_code_gate(context_name="cm", dry_run=False)

        run_gate_command_mock.assert_called_once_with(
            ["env", "TESTKIT_PROFILE=gate", "uv", "run", "test", "run", "--json", "--stack", "cm"],
            dry_run=False,
        )

    @staticmethod
    def test_gate_policy_allows_testing_test_gate() -> None:
        _validate_target_gate_policy(
            target_definition=DokployTargetDefinition(
                context="cm",
                instance="testing",
                require_test_gate=True,
            )
        )

    def test_gate_policy_blocks_test_gate_on_dev(self) -> None:
        with self.assertRaises(click.ClickException):
            _validate_target_gate_policy(
                target_definition=DokployTargetDefinition(
                    context="cm",
                    instance="dev",
                    require_test_gate=True,
                )
            )

    @staticmethod
    def test_gate_policy_allows_prod_backup_gate() -> None:
        _validate_target_gate_policy(
            target_definition=DokployTargetDefinition(
                context="opw",
                instance="prod",
                require_prod_gate=True,
            )
        )

    def test_gate_policy_blocks_prod_backup_gate_on_testing(self) -> None:
        with self.assertRaises(click.ClickException):
            _validate_target_gate_policy(
                target_definition=DokployTargetDefinition(
                    context="opw",
                    instance="testing",
                    require_prod_gate=True,
                )
            )


class PlatformDokployRequestTests(unittest.TestCase):
    def test_dokploy_request_wraps_list_payload(self) -> None:
        with patch("tools.platform.cli.platform_dokploy.dokploy_request", return_value=[{"id": "deployment-1"}]):
            payload = _dokploy_request(
                host="https://dokploy.example",
                token="token",
                path="/api/deployment.allByType",
            )

        self.assertEqual(payload, {"data": [{"id": "deployment-1"}]})

    def test_dokploy_request_rejects_scalar_payload(self) -> None:
        with patch("tools.platform.cli.platform_dokploy.dokploy_request", return_value="not-json-object"):
            with self.assertRaises(click.ClickException) as captured_error:
                _dokploy_request(
                    host="https://dokploy.example",
                    token="token",
                    path="/api/deployment.allByType",
                )

        self.assertIn("unsupported scalar payload", captured_error.exception.message)


if __name__ == "__main__":
    unittest.main()
