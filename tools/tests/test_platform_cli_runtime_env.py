"""Regression tests for platform runtime environment generation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.platform_cli import (
    ContextDefinition,
    DokployTargetDefinition,
    InstanceDefinition,
    RuntimeSelection,
    StackDefinition,
    _build_runtime_env_values,
    _load_environment,
    _resolve_ship_health_timeout_seconds,
    _resolve_ship_healthcheck_urls,
    _resolve_ship_timeout_seconds,
    _run_with_web_temporarily_stopped,
)


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
    def test_runtime_env_excludes_admin_credential_keys(self) -> None:
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
                "RESTORE_SSH_KEY": "/root/.ssh/id_rsa",
                "ODOO_RESTORE_LOCK_FILE": "/volumes/data/.restore_in_progress",
                "ODOO_RESTORE_LOCK_TIMEOUT_SECONDS": "7200",
            },
        )

        self.assertNotIn("ODOO_ADMIN_LOGIN", runtime_values)
        self.assertNotIn("ODOO_ADMIN_PASSWORD", runtime_values)
        self.assertEqual(runtime_values.get("ODOO_KEY"), "key-from-source")
        self.assertEqual(runtime_values.get("ODOO_UPSTREAM_HOST"), "opw-prod.shiny")
        self.assertEqual(runtime_values.get("RESTORE_SSH_KEY"), "/root/.ssh/id_rsa")
        self.assertEqual(
            runtime_values.get("ODOO_RESTORE_LOCK_FILE"),
            "/volumes/data/.restore_in_progress",
        )

    def test_runtime_env_sets_restore_defaults(self) -> None:
        runtime_values = _build_runtime_env_values(
            runtime_env_file=Path("/tmp/cm.local.env"),
            stack_definition=_sample_stack_definition(),
            runtime_selection=_sample_runtime_selection(),
            source_environment={
                "ODOO_DB_USER": "odoo",
                "ODOO_DB_PASSWORD": "database-password",
            },
        )

        self.assertEqual(runtime_values.get("ODOO_FILESTORE_PATH"), "/volumes/data/filestore")
        self.assertEqual(
            runtime_values.get("ODOO_RESTORE_LOCK_FILE"),
            "/volumes/data/.restore_in_progress",
        )
        self.assertEqual(runtime_values.get("ODOO_RESTORE_LOCK_TIMEOUT_SECONDS"), "7200")

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
            patch("tools.platform_cli._compose_base_command", return_value=["docker", "compose"]),
            patch(
                "tools.platform_cli._run_command_best_effort",
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
            patch("tools.platform_cli._compose_base_command", return_value=["docker", "compose"]),
            patch(
                "tools.platform_cli._run_command_best_effort",
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
            healthcheck_path="/web/health",
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


if __name__ == "__main__":
    unittest.main()
