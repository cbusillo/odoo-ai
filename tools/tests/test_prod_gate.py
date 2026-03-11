from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click import ClickException

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
            with patch.dict(os.environ, {"CM_PROD_BACKUP_STORAGE": ""}, clear=True), patch(
                "pathlib.Path.cwd", return_value=repo_root
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_BACKUP_STORAGE", required=True), "pbs-backup")

    def test_env_prefers_repo_dotenv_over_process_value_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("CM_PROD_PROXMOX_HOST=repo-host\n", encoding="utf-8")
            with patch.dict(os.environ, {"CM_PROD_PROXMOX_HOST": "shell-host"}, clear=True), patch(
                "pathlib.Path.cwd", return_value=repo_root
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_PROXMOX_HOST", required=True), "repo-host")

    def test_env_uses_process_value_when_repo_dotenv_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text("OTHER_KEY=1\n", encoding="utf-8")
            with patch.dict(os.environ, {"CM_PROD_PROXMOX_HOST": "shell-host"}, clear=True), patch(
                "pathlib.Path.cwd", return_value=repo_root
            ):
                self.assertEqual(prod_gate._env("CM", "PROD_PROXMOX_HOST", required=True), "shell-host")

    def test_env_raises_when_required_value_missing_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".git").mkdir()
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=repo_root):
                with self.assertRaises(ClickException):
                    prod_gate._env("CM", "PROD_CT_ID", required=True)


if __name__ == "__main__":
    unittest.main()
