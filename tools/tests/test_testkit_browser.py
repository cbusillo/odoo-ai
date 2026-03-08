import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.testkit import browser


class TestkitBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        browser.reset_script_runner_restart_cache()

    def test_restart_script_runner_runs_once_per_project(self) -> None:
        success_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with (
            patch("tools.testkit.browser.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.browser._cross_process_restart_lock", return_value=contextlib.nullcontext()),
            patch("tools.testkit.browser.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.browser.subprocess.run", return_value=success_result) as run_mock,
        ):
            browser.restart_script_runner_with_orphan_cleanup()
            browser.restart_script_runner_with_orphan_cleanup()

        self.assertEqual(run_mock.call_count, 1)
        command = run_mock.call_args.args[0]
        self.assertEqual(command, ["docker", "compose", "up", "-d", "--remove-orphans", "script-runner"])

    def test_restart_script_runner_runs_for_each_project(self) -> None:
        success_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with (
            patch(
                "tools.testkit.browser.compose_env",
                side_effect=[{"ODOO_PROJECT_NAME": "odoo-opw"}, {"ODOO_PROJECT_NAME": "odoo-cm"}],
            ),
            patch("tools.testkit.browser._cross_process_restart_lock", return_value=contextlib.nullcontext()),
            patch("tools.testkit.browser.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.browser.subprocess.run", return_value=success_result) as run_mock,
        ):
            browser.restart_script_runner_with_orphan_cleanup()
            browser.restart_script_runner_with_orphan_cleanup()

        self.assertEqual(run_mock.call_count, 2)

    def test_restart_script_runner_raises_on_compose_failure(self) -> None:
        failure_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with (
            patch("tools.testkit.browser.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.browser._cross_process_restart_lock", return_value=contextlib.nullcontext()),
            patch("tools.testkit.browser.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.browser.subprocess.run", return_value=failure_result),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                browser.restart_script_runner_with_orphan_cleanup()

        self.assertIn("Failed to refresh testkit service", str(error_context.exception))

    def test_restart_script_runner_uses_stack_name_fallback(self) -> None:
        success_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with (
            patch("tools.testkit.browser.compose_env", return_value={"ODOO_STACK_NAME": "odoo-qc-local"}),
            patch("tools.testkit.browser._cross_process_restart_lock", return_value=contextlib.nullcontext()),
            patch("tools.testkit.browser.get_script_runner_service", return_value="script-runner"),
            patch("tools.testkit.browser.subprocess.run", return_value=success_result) as run_mock,
        ):
            browser.restart_script_runner_with_orphan_cleanup()
            browser.restart_script_runner_with_orphan_cleanup()

        self.assertEqual(run_mock.call_count, 1)

    def test_restart_script_runner_raises_on_timeout(self) -> None:
        with (
            patch("tools.testkit.browser.compose_env", return_value={"ODOO_PROJECT_NAME": "odoo-opw"}),
            patch("tools.testkit.browser._cross_process_restart_lock", return_value=contextlib.nullcontext()),
            patch("tools.testkit.browser.get_script_runner_service", return_value="script-runner"),
            patch(
                "tools.testkit.browser.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["docker", "compose"], timeout=60),
            ),
        ):
            with self.assertRaises(RuntimeError) as error_context:
                browser.restart_script_runner_with_orphan_cleanup()

        self.assertIn("Timed out while refreshing testkit service", str(error_context.exception))

    def test_cross_process_restart_lock_creates_lockfile_and_unlocks(self) -> None:
        class FakeFcntl:
            LOCK_EX = 1
            LOCK_UN = 2

            def __init__(self) -> None:
                self.calls: list[int] = []

            def flock(self, _file_descriptor: int, lock_flag: int) -> None:
                self.calls.append(lock_flag)

        fake_fcntl = FakeFcntl()
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_environment = {"ODOO_STATE_ROOT": tempdir, "ODOO_PROJECT_NAME": "odoo-opw"}
            with patch("tools.testkit.browser.fcntl", fake_fcntl):
                with browser._cross_process_restart_lock(runtime_environment):
                    pass

            lock_path = Path(tempdir) / browser._SCRIPT_RUNNER_RESTART_LOCK_FILENAME
            self.assertTrue(lock_path.exists())
            self.assertEqual(fake_fcntl.calls, [fake_fcntl.LOCK_EX, fake_fcntl.LOCK_UN])


if __name__ == "__main__":
    unittest.main()
