import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from click import ClickException
from click.testing import CliRunner

from tools import prod_gate


class ProdGateEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        prod_gate._repo_env_defaults.cache_clear()

    def tearDown(self) -> None:
        prod_gate._repo_env_defaults.cache_clear()

    def test_env_uses_repo_dotenv_when_process_value_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("CM_PROD_CT_ID=200\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=repo_root):
                self.assertEqual(prod_gate._env("CM", "PROD_CT_ID", required=True), "200")

    def test_env_uses_repo_dotenv_when_process_value_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("CM_PROD_BACKUP_STORAGE=pbs-backup\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"CM_PROD_BACKUP_STORAGE": ""}, clear=True),
                patch("pathlib.Path.cwd", return_value=repo_root),
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_BACKUP_STORAGE", required=True), "pbs-backup")

    def test_env_prefers_process_value_over_repo_dotenv_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("CM_PROD_PROXMOX_HOST=repo-host\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"CM_PROD_PROXMOX_HOST": "shell-host"}, clear=True),
                patch("pathlib.Path.cwd", return_value=repo_root),
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_PROXMOX_HOST", required=True), "shell-host")

    def test_env_uses_process_value_when_repo_dotenv_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("OTHER_KEY=1\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"CM_PROD_PROXMOX_HOST": "shell-host"}, clear=True),
                patch("pathlib.Path.cwd", return_value=repo_root),
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_PROXMOX_HOST", required=True), "shell-host")

    def test_env_raises_when_required_value_missing_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=repo_root):
                with self.assertRaises(ClickException):
                    prod_gate._env("CM", "PROD_CT_ID", required=True)


class ProdGateBackupCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        prod_gate._repo_env_defaults.cache_clear()

    def tearDown(self) -> None:
        prod_gate._repo_env_defaults.cache_clear()

    def test_backup_command_writes_control_plane_record_after_successful_backup(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            fixed_datetime = datetime(2026, 4, 10, 18, 22, 31)
            captured_commands: list[list[str]] = []

            class FrozenDateTime:
                @staticmethod
                def utcnow() -> datetime:
                    return fixed_datetime

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_PROXMOX_HOST": "prox-main",
                        "CM_PROD_PROXMOX_USER": "root",
                        "CM_PROD_CT_ID": "111",
                        "CM_PROD_BACKUP_STORAGE": "pbs",
                        "CM_PROD_BACKUP_MODE": "both",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
                patch("tools.prod_gate.datetime", FrozenDateTime),
                patch(
                    "tools.prod_gate._run",
                    side_effect=lambda command, cwd=None, dry_run=False: captured_commands.append(command),
                ),
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                        "--tag",
                        "cutover",
                        "--control-plane-record-dir",
                        "tmp/prod-gates",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertEqual(
                captured_commands,
                [
                    ["ssh", "root@prox-main", "pct", "snapshot", "111", "cm-predeploy-20260410-182231-cutover"],
                    ["ssh", "root@prox-main", "vzdump", "111", "--mode", "snapshot", "--storage", "pbs"],
                ],
            )
            record_path = repo_root / "tmp" / "prod-gates" / "backup-cm-prod-20260410T182231Z.json"
            self.assertTrue(record_path.exists())
            persisted_payload = record_path.read_text(encoding="utf-8")
            self.assertIn('"context": "cm"', persisted_payload)
            self.assertIn('"instance": "prod"', persisted_payload)
            self.assertIn('"snapshot": "cm-predeploy-20260410-182231-cutover"', persisted_payload)
            self.assertIn('"storage": "pbs"', persisted_payload)
            self.assertIn('"tag": "cutover"', persisted_payload)
            self.assertIn('"status": "pass"', persisted_payload)

    def test_backup_command_skips_record_write_on_dry_run(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_PROXMOX_HOST": "prox-main",
                        "CM_PROD_PROXMOX_USER": "root",
                        "CM_PROD_CT_ID": "111",
                        "CM_PROD_BACKUP_STORAGE": "pbs",
                        "CM_PROD_BACKUP_MODE": "snapshot",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                        "--control-plane-record-dir",
                        "tmp/prod-gates",
                        "--dry-run",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("control_plane_record_skipped=dry_run", result.output)
            self.assertFalse((repo_root / "tmp" / "prod-gates").exists())

    def test_backup_command_skips_control_plane_record_when_backup_mode_is_none(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_PROXMOX_HOST": "prox-main",
                        "CM_PROD_PROXMOX_USER": "root",
                        "CM_PROD_CT_ID": "111",
                        "CM_PROD_BACKUP_MODE": "none",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
                patch("tools.prod_gate._run") as run_mock,
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                        "--control-plane-record-dir",
                        "tmp/prod-gates",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("control_plane_record_skipped=no_backup_mode", result.output)
            run_mock.assert_not_called()
            self.assertFalse((repo_root / "tmp" / "prod-gates").exists())

    def test_backup_command_still_runs_tests_before_skipping_record_when_backup_mode_is_none(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            captured_commands: list[list[str]] = []

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_PROXMOX_HOST": "prox-main",
                        "CM_PROD_PROXMOX_USER": "root",
                        "CM_PROD_CT_ID": "111",
                        "CM_PROD_BACKUP_MODE": "none",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
                patch(
                    "tools.prod_gate._run", side_effect=lambda command, cwd=None, dry_run=False: captured_commands.append(command)
                ),
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                        "--run-tests",
                        "--control-plane-record-dir",
                        "tmp/prod-gates",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("control_plane_record_skipped=no_backup_mode", result.output)
            self.assertEqual(captured_commands, [["uv", "run", "test", "run", "--json", "--stack", "cm"]])

    def test_backup_command_is_noop_when_backup_mode_is_none_and_no_record_requested(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_BACKUP_MODE": "none",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
                patch("tools.prod_gate._run") as run_mock,
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            run_mock.assert_not_called()
            self.assertFalse((repo_root / "tmp" / "prod-gates").exists())

    def test_backup_command_rejects_unknown_backup_mode_before_running_backups_or_writing_record(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()

            with (
                patch.dict(
                    os.environ,
                    {
                        "CM_PROD_BACKUP_MODE": "snapshot,invalid-mode",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.cwd", return_value=repo_root),
                patch("tools.prod_gate._run") as run_mock,
            ):
                result = runner.invoke(
                    prod_gate.main,
                    [
                        "backup",
                        "--target",
                        "cm",
                        "--control-plane-record-dir",
                        "tmp/prod-gates",
                    ],
                )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Invalid PROD_BACKUP_MODE value(s): invalid-mode", result.output)
            run_mock.assert_not_called()
            self.assertFalse((repo_root / "tmp" / "prod-gates").exists())


if __name__ == "__main__":
    unittest.main()
