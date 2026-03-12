from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_startup_module() -> types.ModuleType:
    module_path = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "run_odoo_startup.py"
    spec = importlib.util.spec_from_file_location("run_odoo_startup_test_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    psycopg2_module = types.ModuleType("psycopg2")

    def _unexpected_connect(*unused_args: object, **unused_kwargs: object) -> None:
        _ = unused_args, unused_kwargs
        raise AssertionError("psycopg2.connect should not be called in this test")

    psycopg2_module.connect = _unexpected_connect

    with patch.dict(sys.modules, {"psycopg2": psycopg2_module}):
        spec.loader.exec_module(module)
    return module


odoo_startup = _load_startup_module()


class OdooStartupAdminPolicyTests(unittest.TestCase):
    def test_load_settings_reads_admin_credentials(self) -> None:
        environment = {
            "ODOO_DB_NAME": "cm",
            "ODOO_DB_HOST": "database",
            "ODOO_DB_PORT": "5432",
            "ODOO_DB_USER": "odoo",
            "ODOO_DB_PASSWORD": "database-password",
            "ODOO_MASTER_PASSWORD": "master-password",
            "ODOO_ADDONS_PATH": "/odoo/addons",
            "ODOO_ADMIN_LOGIN": "admin",
            "ODOO_ADMIN_PASSWORD": "secure-password",
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = odoo_startup._load_settings(argparse.Namespace(config_path="/tmp/generated.conf"))

        self.assertEqual(settings.admin_login, "admin")
        self.assertEqual(settings.admin_password, "secure-password")

    def test_apply_admin_password_uses_write_script(self) -> None:
        settings = odoo_startup.StartupSettings(
            config_path="/tmp/generated.conf",
            base_config_path="/tmp/base.conf",
            database_name="cm",
            database_host="database",
            database_port=5432,
            database_user="odoo",
            database_password="database-password",
            master_password="master-password",
            admin_login="admin",
            admin_password="secure-password",
            addons_path="/odoo/addons",
            data_dir="/volumes/data",
            list_db="False",
            install_modules=("cm_custom",),
            data_workflow_lock_file="/volumes/data/.data_workflow_in_progress",
            data_workflow_lock_timeout_seconds=7200,
            ready_timeout_seconds=180,
            poll_interval_seconds=2.0,
        )
        captured_calls: list[dict[str, object]] = []

        def _capture_run(command: list[str], input: bytes, check: bool) -> None:
            captured_calls.append({"command": command, "input": input.decode(), "check": check})

        with patch.object(odoo_startup.subprocess, "run", side_effect=_capture_run):
            odoo_startup._apply_admin_password_if_configured(settings)

        self.assertEqual(len(captured_calls), 1)
        self.assertIn("write({'password': payload['password']})", str(captured_calls[0]["input"]))
        self.assertIn("secure-password", str(captured_calls[0]["input"]))

    def test_apply_environment_overrides_runs_override_script(self) -> None:
        settings = odoo_startup.StartupSettings(
            config_path="/tmp/generated.conf",
            base_config_path="/tmp/base.conf",
            database_name="cm",
            database_host="database",
            database_port=5432,
            database_user="odoo",
            database_password="database-password",
            master_password="master-password",
            admin_login="admin",
            admin_password="",
            addons_path="/odoo/addons",
            data_dir="/volumes/data",
            list_db="False",
            install_modules=("cm_custom",),
            data_workflow_lock_file="/volumes/data/.data_workflow_in_progress",
            data_workflow_lock_timeout_seconds=7200,
            ready_timeout_seconds=180,
            poll_interval_seconds=2.0,
        )
        captured_calls: list[dict[str, object]] = []

        def _capture_run(command: list[str], input: bytes, check: bool) -> None:
            captured_calls.append({"command": command, "input": input.decode(), "check": check})

        with patch.object(odoo_startup.subprocess, "run", side_effect=_capture_run):
            odoo_startup._apply_environment_overrides_if_available(settings)

        self.assertEqual(len(captured_calls), 1)
        self.assertIn("environment.overrides", str(captured_calls[0]["input"]))
        self.assertIn("authentik.sso.config", str(captured_calls[0]["input"]))


if __name__ == "__main__":
    unittest.main()
