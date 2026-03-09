from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace, TracebackType
from unittest.mock import patch


def _load_data_workflow_module() -> types.ModuleType:
    module_path = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "run_odoo_data_workflows.py"
    spec = importlib.util.spec_from_file_location("run_odoo_data_workflows_test_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)

    psycopg2_module = types.ModuleType("psycopg2")
    psycopg2_sql_module = types.ModuleType("psycopg2.sql")
    psycopg2_extensions_module = types.ModuleType("psycopg2.extensions")

    class _FakePsycopgError(Exception):
        pass

    def _unexpected_connect(*unused_args: object, **unused_kwargs: object) -> None:
        _ = unused_args, unused_kwargs
        raise AssertionError("psycopg2.connect should not be called in this test")

    psycopg2_module.sql = psycopg2_sql_module
    psycopg2_module.Error = _FakePsycopgError
    psycopg2_module.connect = _unexpected_connect
    psycopg2_extensions_module.connection = object

    passlib_module = types.ModuleType("passlib")
    passlib_context_module = types.ModuleType("passlib.context")

    class _FakeCryptContext:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    passlib_context_module.CryptContext = _FakeCryptContext

    temporary_modules = {
        "psycopg2": psycopg2_module,
        "psycopg2.sql": psycopg2_sql_module,
        "psycopg2.extensions": psycopg2_extensions_module,
        "passlib": passlib_module,
        "passlib.context": passlib_context_module,
    }
    with patch.dict(sys.modules, temporary_modules):
        spec.loader.exec_module(module)
    return module


odoo_data_workflow = _load_data_workflow_module()


class _FakeCursor:
    def __init__(self) -> None:
        self._query = ""

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def execute(self, query: str, _params: tuple[object, ...]) -> None:
        self._query = query

    def fetchone(self) -> tuple[int,int] | tuple[str] | None:
        if "FROM res_users" in self._query:
            return 1, 2
        if "FROM res_partner" in self._query:
            return "admin@localhost",
        return None


class _FakeConnection:
    @staticmethod
    def cursor() -> _FakeCursor:
        return _FakeCursor()


class DataWorkflowAdminPolicyTests(unittest.TestCase):
    def test_local_server_settings_defaults_admin_login_to_admin(self) -> None:
        settings = odoo_data_workflow.LocalServerSettings(
            ODOO_DB_HOST="database",
            ODOO_DB_USER="odoo",
            ODOO_DB_PASSWORD="database-password",
            ODOO_DB_NAME="cm",
            ODOO_FILESTORE_PATH="/tmp/filestore",
        )

        self.assertEqual(settings.admin_login, "admin")

    def test_ensure_admin_user_validates_default_admin_password_without_password_override(self) -> None:
        command_labels: list[str] = []
        workflow_runner = odoo_data_workflow.OdooDataWorkflowRunner.__new__(odoo_data_workflow.OdooDataWorkflowRunner)
        workflow_runner.local = SimpleNamespace(
            db_name="cm",
            admin_login="",
            admin_password=None,
            db_conn=_FakeConnection(),
        )
        workflow_runner.connect_to_db = lambda: None
        workflow_runner._reset_db_connection = lambda: None
        workflow_runner._run_odoo_shell = lambda _script, label: command_labels.append(label)

        workflow_runner.ensure_admin_user()

        self.assertEqual(command_labels, ["admin password policy"])

    def test_ensure_admin_user_uses_write_for_password_hardening(self) -> None:
        executed_scripts: list[tuple[str, str]] = []
        workflow_runner = odoo_data_workflow.OdooDataWorkflowRunner.__new__(odoo_data_workflow.OdooDataWorkflowRunner)
        workflow_runner.local = SimpleNamespace(
            db_name="cm",
            admin_login="admin",
            admin_password=SimpleNamespace(get_secret_value=lambda: "secure-password"),
            db_conn=_FakeConnection(),
        )
        workflow_runner.connect_to_db = lambda: None
        workflow_runner._reset_db_connection = lambda: None
        workflow_runner._run_odoo_shell = lambda script, label: executed_scripts.append((label, script))

        workflow_runner.ensure_admin_user()

        hardening_script = next(script for label, script in executed_scripts if label == "admin hardening")
        self.assertIn("write({'password': payload['password']})", hardening_script)


if __name__ == "__main__":
    unittest.main()
