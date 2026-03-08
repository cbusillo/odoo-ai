"""Regression tests for testkit validation helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.testkit import validate


class TestkitValidateTests(unittest.TestCase):
    def test_source_counts_only_include_static_js_tests(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            addons_root = Path(temporary_directory_name) / "addons"
            module_root = addons_root / "demo_module"
            (module_root / "__manifest__.py").parent.mkdir(parents=True, exist_ok=True)
            (module_root / "__manifest__.py").write_text("{}\n", encoding="utf-8")

            static_tests_directory = module_root / "static" / "tests"
            static_tests_directory.mkdir(parents=True, exist_ok=True)
            (static_tests_directory / "widget.test.js").write_text("test('widget', () => {});\n", encoding="utf-8")

            non_static_directory = module_root / "tests" / "js"
            non_static_directory.mkdir(parents=True, exist_ok=True)
            (non_static_directory / "legacy.test.js").write_text("test('legacy', () => {});\n", encoding="utf-8")

            counts = validate._source_counts(addons_root)

        self.assertEqual(counts["js"], 1)

    def test_missing_tagged_tests_checks_nested_phase_directories(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            addons_root = Path(temporary_directory_name) / "addons"
            nested_test_file = addons_root / "demo_module" / "tests" / "unit" / "nested" / "test_nested.py"
            nested_test_file.parent.mkdir(parents=True, exist_ok=True)
            nested_test_file.write_text("def test_nested():\n    assert True\n", encoding="utf-8")

            missing = validate._missing_tagged_tests(addons_root)

        self.assertIn(str(nested_test_file), missing["unit"])

    def test_missing_test_package_inits_checks_nested_directories(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            addons_root = Path(temporary_directory_name) / "addons"
            phase_directory = addons_root / "demo_module" / "tests" / "unit"
            phase_directory.mkdir(parents=True, exist_ok=True)
            (phase_directory / "__init__.py").write_text("\n", encoding="utf-8")

            nested_directory = phase_directory / "nested"
            nested_directory.mkdir(parents=True, exist_ok=True)
            (nested_directory / "test_nested.py").write_text("def test_nested():\n    assert True\n", encoding="utf-8")

            missing = validate._missing_test_package_inits(addons_root)

        self.assertIn(str(nested_directory), missing["unit"])


if __name__ == "__main__":
    unittest.main()
