from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


def _load_restore_module() -> types.ModuleType:
    module_path = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "restore_from_upstream.py"
    if "psycopg2" not in sys.modules:
        psycopg2_module = types.ModuleType("psycopg2")
        psycopg2_sql_module = types.ModuleType("psycopg2.sql")
        psycopg2_extensions_module = types.ModuleType("psycopg2.extensions")
        setattr(psycopg2_module, "sql", psycopg2_sql_module)
        setattr(psycopg2_extensions_module, "connection", object)
        sys.modules["psycopg2"] = psycopg2_module
        sys.modules["psycopg2.sql"] = psycopg2_sql_module
        sys.modules["psycopg2.extensions"] = psycopg2_extensions_module
    if "passlib" not in sys.modules:
        passlib_module = types.ModuleType("passlib")
        passlib_context_module = types.ModuleType("passlib.context")

        class _FakeCryptContext:
            def __init__(self, *args, **kwargs) -> None:
                pass

        setattr(passlib_context_module, "CryptContext", _FakeCryptContext)
        sys.modules["passlib"] = passlib_module
        sys.modules["passlib.context"] = passlib_context_module
    spec = importlib.util.spec_from_file_location("restore_from_upstream_test_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


restore_from_upstream = _load_restore_module()


class _FakeCursor:
    def __init__(self) -> None:
        self._query = ""

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
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


class RestoreAdminPolicyTests(unittest.TestCase):
    def test_local_server_settings_defaults_admin_login_to_admin(self) -> None:
        settings = restore_from_upstream.LocalServerSettings(
            ODOO_DB_HOST="database",
            ODOO_DB_USER="odoo",
            ODOO_DB_PASSWORD="database-password",
            ODOO_DB_NAME="cm",
            ODOO_FILESTORE_PATH="/tmp/filestore",
        )

        self.assertEqual(settings.admin_login, "admin")

    def test_ensure_admin_user_validates_default_admin_password_without_password_override(self) -> None:
        command_labels: list[str] = []
        restorer = restore_from_upstream.OdooUpstreamRestorer.__new__(restore_from_upstream.OdooUpstreamRestorer)
        restorer.local = SimpleNamespace(
            db_name="cm",
            admin_login="",
            admin_password=None,
            db_conn=_FakeConnection(),
        )
        restorer.connect_to_db = lambda: None
        restorer._reset_db_connection = lambda: None
        restorer._run_odoo_shell = lambda _script, label: command_labels.append(label)

        restorer.ensure_admin_user()

        self.assertEqual(command_labels, ["admin password policy"])


if __name__ == "__main__":
    unittest.main()
