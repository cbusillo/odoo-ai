from contextlib import chdir
import json
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
import click
from unittest.mock import patch

from click.testing import CliRunner

from tools.testkit.cli import test as test_command_group


def _as_click_command(command: object) -> click.Command:
    assert isinstance(command, click.Command)
    return command


class TestkitRerunFailuresTests(unittest.TestCase):
    def test_rerun_failures_forwards_json_flag_to_child_run(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temporary_directory_name:
            temporary_directory = Path(temporary_directory_name)
            with chdir(temporary_directory):
                phase_directory = Path("tmp") / "test-logs" / "latest" / "unit"
                phase_directory.mkdir(parents=True, exist_ok=True)
                (phase_directory / "unit-0.summary.json").write_text(
                    json.dumps({"returncode": 1, "modules": ["demo_module"]}),
                    encoding="utf-8",
                )

                captured_command: dict[str, list[str]] = {}

                def _fake_call(command: list[str]) -> int:
                    captured_command["command"] = command
                    return 0

                with (
                    patch("tools.testkit.cli._apply_stack_env"),
                    patch("subprocess.call", side_effect=_fake_call),
                ):
                    result = runner.invoke(
                        _as_click_command(test_command_group),
                        ["rerun-failures", "--stack", "opw", "--json"],
                        catch_exceptions=False,
                    )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("command", captured_command)
        self.assertIn("--json", captured_command["command"])


if __name__ == "__main__":
    unittest.main()
