"""Regression tests for testkit auth bootstrap."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

from tools.testkit.auth import setup_test_authentication


class TestkitAuthTests(unittest.TestCase):
    def test_setup_test_authentication_hashes_and_updates_admin_password(self) -> None:
        hash_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="pbkdf2$hash\n", stderr="")
        update_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="UPDATE 1\n", stderr="")
        with (
            patch("tools.testkit.auth.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.auth.ensure_services_up"),
            patch("tools.testkit.auth.get_database_service", return_value="database"),
            patch("tools.testkit.auth.get_db_user", return_value="odoo"),
            patch("tools.testkit.auth.compose_exec", side_effect=[hash_result, update_result]) as compose_exec_mock,
            patch.dict(os.environ, {}, clear=True),
        ):
            generated_password = setup_test_authentication("odoo-test")
            self.assertEqual(os.environ.get("ODOO_TEST_PASSWORD"), generated_password)

        self.assertEqual(len(generated_password), 16)
        hash_call = compose_exec_mock.call_args_list[0]
        self.assertEqual(hash_call.args[0], "script-runner")
        self.assertEqual(hash_call.args[1][0], "env")
        self.assertTrue(hash_call.args[1][1].startswith("TESTKIT_PASS="))
        update_call = compose_exec_mock.call_args_list[1]
        self.assertEqual(update_call.args[0], "database")
        update_sql = update_call.args[1][-1]
        self.assertIn("UPDATE res_users", update_sql)
        self.assertIn("password='pbkdf2$hash'", update_sql)
        self.assertIn("WHERE login='admin';", update_sql)

    def test_setup_test_authentication_fails_when_hashing_fails(self) -> None:
        hash_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing passlib")
        with (
            patch("tools.testkit.auth.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.auth.ensure_services_up"),
            patch("tools.testkit.auth.compose_exec", return_value=hash_result) as compose_exec_mock,
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaises(RuntimeError):
                setup_test_authentication("odoo-test")

        self.assertEqual(compose_exec_mock.call_count, 1)

    def test_setup_test_authentication_fails_when_password_update_fails(self) -> None:
        hash_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="pbkdf2$hash\n", stderr="")
        update_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="permission denied")
        with (
            patch("tools.testkit.auth.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.auth.ensure_services_up"),
            patch("tools.testkit.auth.get_database_service", return_value="database"),
            patch("tools.testkit.auth.get_db_user", return_value="odoo"),
            patch("tools.testkit.auth.compose_exec", side_effect=[hash_result, update_result]),
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                setup_test_authentication("odoo-test")

        self.assertIn("Unable to persist hashed test admin password", str(error_context.exception))
        self.assertNotIn("ODOO_TEST_PASSWORD", os.environ)

if __name__ == "__main__":
    unittest.main()
