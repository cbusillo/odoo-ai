from typing import Any

from psycopg2.errors import InFailedSqlTransaction
from odoo.modules import module as odoo_module

from ..common_imports import tagged, patch, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestTransactionMixin(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.test_model = self.env["transaction.mixin"]

    def test_safe_commit_in_test_mode(self) -> None:
        with patch.object(self.test_model.env.cr, "commit") as mock_commit:
            self.test_model._safe_commit()
            mock_commit.assert_not_called()

    def test_safe_rollback_in_test_mode(self) -> None:
        with patch.object(self.test_model.env.cr, "rollback") as mock_rollback:
            self.test_model._safe_rollback()
            mock_rollback.assert_not_called()

    def test_safe_commit_outside_test_mode(self) -> None:
        from odoo.tools import config

        with patch.object(odoo_module, "current_test", False):
            with patch.object(config, "get", return_value=False):
                with patch.object(self.test_model.env.cr, "commit") as mock_commit:
                    self.test_model._safe_commit()
                    mock_commit.assert_called_once()

    def test_safe_rollback_outside_test_mode(self) -> None:
        from odoo.tools import config

        with patch.object(odoo_module, "current_test", False):
            with patch.object(config, "get", return_value=False):
                with patch.object(self.test_model.env.cr, "rollback") as mock_rollback:
                    self.test_model._safe_rollback()
                    mock_rollback.assert_called_once()

    def test_is_test_mode_detection_methods(self) -> None:
        from odoo.tools import config

        module_test_mode = bool(odoo_module.current_test)
        config_test_enable = bool(config.get("test_enable"))
        is_test_mode = self.test_model._is_test_mode()

        any_test_mode = module_test_mode or config_test_enable
        self.assertTrue(
            any_test_mode,
            f"At least one test detection method should work. Module: {module_test_mode}, Config: {config_test_enable}",
        )

        self.assertTrue(is_test_mode, "_is_test_mode() should return True during tests")

    def test_new_cursor_context_in_test_mode(self) -> None:
        with self.test_model._new_cursor_context() as new_env:
            self.assertIsNotNone(new_env)
            self.assertNotEqual(new_env.cr, self.test_model.env.cr)

            new_env["res.partner"].create({"name": "Test Partner in New Cursor", "email": "test_new_cursor@example.com"})

        partner = self.env["res.partner"].search([("email", "=", "test_new_cursor@example.com")])
        self.assertFalse(partner, "Partner should not exist in main cursor because no commit in test mode")

    def test_advisory_lock(self) -> None:
        with self.test_model._advisory_lock(12345) as acquired:
            self.assertTrue(acquired, "Should acquire advisory lock")

        self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", [12345])
        self.assertTrue(self.env.cr.fetchone()[0], "Lock should be released")
        self.env.cr.execute("SELECT pg_advisory_unlock(%s)", [12345])

    def test_advisory_lock_with_failed_transaction(self) -> None:
        original_execute = self.env.cr.execute
        unlock_call_count = 0

        def mock_execute(query: str, params: list | None = None) -> Any:
            nonlocal unlock_call_count
            if "pg_try_advisory_lock" in query:
                return original_execute(query, params)
            if "pg_advisory_unlock" in query:
                unlock_call_count += 1
                raise InFailedSqlTransaction("current transaction is aborted")
            return original_execute(query, params)

        with patch.object(self.env.cr, "execute", side_effect=mock_execute):
            with self.test_model._advisory_lock(12346) as acquired:
                self.assertTrue(acquired, "Should acquire advisory lock")

            self.assertEqual(unlock_call_count, 1, "Should have attempted to unlock")

        self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", [12346])
        lock_available = self.env.cr.fetchone()[0]
        if lock_available:
            self.env.cr.execute("SELECT pg_advisory_unlock(%s)", [12346])
