"""Regression tests for platform runtime selection guards."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.platform import runtime
from tools.platform.models import ContextDefinition, InstanceDefinition, StackDefinition


def _sample_stack_definition() -> StackDefinition:
    return StackDefinition(
        schema_version=1,
        odoo_version="19.0",
        addons_path=("/odoo/addons",),
        contexts={
            "cm": ContextDefinition(
                instances={
                    "local": InstanceDefinition(),
                    "dev": InstanceDefinition(),
                    "testing": InstanceDefinition(),
                    "prod": InstanceDefinition(),
                }
            ),
        },
    )


class PlatformRuntimeSelectionTests(unittest.TestCase):
    def test_resolve_runtime_selection_rejects_unknown_instance(self) -> None:
        with self.assertRaises(ValueError) as captured_error:
            runtime.resolve_runtime_selection(
                _sample_stack_definition(),
                "cm",
                "oops",
                lambda _path: Path("/tmp"),
            )

        self.assertIn("Unknown instance 'oops' for context 'cm'", str(captured_error.exception))
        self.assertIn("Available: dev, local, prod, testing", str(captured_error.exception))

    def test_resolve_runtime_selection_rejects_unknown_context(self) -> None:
        with self.assertRaises(ValueError) as captured_error:
            runtime.resolve_runtime_selection(
                _sample_stack_definition(),
                "missing",
                "local",
                lambda _path: Path("/tmp"),
            )

        self.assertIn("Unknown context 'missing'", str(captured_error.exception))

    def test_resolve_runtime_selection_accepts_known_instance(self) -> None:
        selection = runtime.resolve_runtime_selection(
            _sample_stack_definition(),
            "cm",
            "local",
            lambda _path: Path("/tmp"),
        )

        self.assertEqual(selection.context_name, "cm")
        self.assertEqual(selection.instance_name, "local")


if __name__ == "__main__":
    unittest.main()

