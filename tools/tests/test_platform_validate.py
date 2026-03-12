"""Regression tests for platform validation scenario wiring."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from tools.platform import cli

platform_cli_command: Any = cli.main


class PlatformValidateCliTests(unittest.TestCase):
    def test_shopify_roundtrip_command_dispatches_to_validator(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            runner = CliRunner()

            with (
                patch("tools.platform.cli._discover_repo_root", return_value=repository_root),
                patch(
                    "tools.platform.cli.validate_shopify_roundtrip.run_validation_command",
                    return_value={"result": "ok", "instance": "testing"},
                ) as run_validation_command_mock,
            ):
                result = runner.invoke(
                    platform_cli_command,
                    ["validate", "shopify-roundtrip", "--context", "opw", "--instance", "testing"],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(json.loads(result.output), {"instance": "testing", "result": "ok"})
        run_validation_command_mock.assert_called_once_with(
            context_name="opw",
            instance_name="testing",
            env_file=None,
            remote_login="gpt-admin",
            repository_root=repository_root,
        )


if __name__ == "__main__":
    unittest.main()
