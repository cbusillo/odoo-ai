"""Regression tests for platform runtime environment generation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.platform_cli import (
    ContextDefinition,
    InstanceDefinition,
    RuntimeSelection,
    StackDefinition,
    _build_runtime_env_values,
    _load_environment,
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
            },
        )

        self.assertNotIn("ODOO_ADMIN_LOGIN", runtime_values)
        self.assertNotIn("ODOO_ADMIN_PASSWORD", runtime_values)
        self.assertEqual(runtime_values.get("ODOO_KEY"), "key-from-source")

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


if __name__ == "__main__":
    unittest.main()

