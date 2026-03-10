"""Regression tests for testkit validation helpers."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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

    def test_validate_treats_count_mismatch_as_diagnostic_when_session_is_green(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            addons_root = repo_root / "addons"
            module_root = addons_root / "demo_module"
            phase_root = module_root / "tests" / "unit"
            phase_root.mkdir(parents=True, exist_ok=True)
            (module_root / "__manifest__.py").write_text("{}\n", encoding="utf-8")
            (module_root / "tests" / "__init__.py").write_text("\n", encoding="utf-8")
            (phase_root / "__init__.py").write_text("\n", encoding="utf-8")
            (phase_root / "test_demo.py").write_text(
                "from odoo.tests import tagged\n\n@tagged('unit_test')\ndef test_demo():\n    assert True\n",
                encoding="utf-8",
            )

            session_dir = repo_root / "tmp" / "test-logs" / "test-demo"
            unit_dir = session_dir / "unit"
            unit_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "results": {
                            "unit": {
                                "counters": {
                                    "tests_run": 0,
                                    "failures": 0,
                                    "errors": 0,
                                    "skips": 0,
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (unit_dir / "demo.summary.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "modules": ["demo_module"],
                        "counters": {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0},
                        "outcome_kind": "success",
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with (
                patch("tools.testkit.validate.discover_repo_root", return_value=repo_root),
                redirect_stdout(output),
            ):
                exit_code = validate.validate(session="test-demo", json_out=True)

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["session_success"])
        self.assertTrue(payload["validation_ok"])
        self.assertFalse(payload["counts_ok"])


if __name__ == "__main__":
    unittest.main()
