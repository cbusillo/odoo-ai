"""Regression tests for environment file parsing helpers."""

from pathlib import Path
import tempfile
import unittest

from tools.environment_files import discover_repo_root, parse_env_lines


class EnvironmentFilesTests(unittest.TestCase):
    def test_parse_env_lines_keeps_hash_inside_quoted_values(self) -> None:
        parsed = parse_env_lines([
            'PASSWORD="secret#123"',
            "TOKEN='abc#def'",
        ])

        self.assertEqual(parsed["PASSWORD"], "secret#123")
        self.assertEqual(parsed["TOKEN"], "abc#def")

    def test_parse_env_lines_strips_unquoted_inline_comments(self) -> None:
        parsed = parse_env_lines([
            "ODOO_DB_HOST=database # comment",
        ])

        self.assertEqual(parsed["ODOO_DB_HOST"], "database")

    def test_parse_env_lines_accepts_export_prefix(self) -> None:
        parsed = parse_env_lines([
            "export ODOO_DB_USER=odoo",
        ])

        self.assertEqual(parsed["ODOO_DB_USER"], "odoo")

    def test_discover_repo_root_prefers_git_root_over_addon_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory).resolve()
            (repo_root / ".git").mkdir()
            addon_tests_directory = repo_root / "addons" / "fishbowl_import" / "tests"
            addon_tests_directory.mkdir(parents=True)
            (repo_root / "addons" / "fishbowl_import" / "pyproject.toml").write_text(
                "[project]\nname='fishbowl-import'\n",
                encoding="utf-8",
            )

            discovered_root = discover_repo_root(addon_tests_directory)

        self.assertEqual(discovered_root, repo_root)


if __name__ == "__main__":
    unittest.main()
