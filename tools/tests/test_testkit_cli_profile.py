"""Regression tests for testkit profile defaults."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import click

from tools.testkit.cli import _apply_test_profile_defaults, _normalize_stack_name


class TestkitProfileDefaultsTests(unittest.TestCase):
    def test_gate_profile_sets_deterministic_environment(self) -> None:
        with patch.dict(os.environ, {"TESTKIT_PROFILE": "gate"}, clear=True):
            _apply_test_profile_defaults()

            self.assertEqual(os.environ.get("UNIT_SHARDS"), "4")
            self.assertEqual(os.environ.get("JS_SHARDS"), "1")
            self.assertEqual(os.environ.get("INTEGRATION_SHARDS"), "2")
            self.assertEqual(os.environ.get("TOUR_SHARDS"), "8")
            self.assertEqual(os.environ.get("TOUR_MAX_PROCS"), "1")
            self.assertEqual(os.environ.get("PHASES_OVERLAP"), "0")
            self.assertEqual(os.environ.get("TEST_MAX_PROCS"), "4")
            self.assertEqual(os.environ.get("TESTKIT_DISABLE_DEV_MODE"), "0")
            self.assertEqual(os.environ.get("ODOO_LIMIT_MEMORY_SOFT"), "2147483648")
            self.assertEqual(os.environ.get("ODOO_LIMIT_MEMORY_HARD"), "3221225472")

    def test_unknown_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"TESTKIT_PROFILE": "surprise"}, clear=True):
            with self.assertRaises(click.ClickException):
                _apply_test_profile_defaults()

    def test_normalize_stack_name_rejects_legacy_continuous_integration_suffix(self) -> None:
        with self.assertRaises(click.ClickException):
            _normalize_stack_name("cm-ci", None)

    def test_normalize_stack_name_adds_local_suffix_when_missing(self) -> None:
        self.assertEqual(_normalize_stack_name("cm", None), "cm-local")

    def test_normalize_stack_name_uses_runtime_env_filename_convention(self) -> None:
        runtime_env_file = Path(".platform/env/opw.local.env")

        self.assertEqual(_normalize_stack_name(None, runtime_env_file), "opw-local")

    def test_normalize_stack_name_fails_closed_for_invalid_runtime_env_filename(self) -> None:
        runtime_env_file = Path(".platform/env/opw.env")

        with self.assertRaises(click.ClickException):
            _normalize_stack_name(None, runtime_env_file)


if __name__ == "__main__":
    unittest.main()
