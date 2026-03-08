"""Regression tests for platform runtime status helpers."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from tools.platform import runtime_status


class PlatformRuntimeStatusTests(unittest.TestCase):
    def test_parse_compose_ps_output_accepts_json_lines(self) -> None:
        raw_output = "\n".join(
            [
                json.dumps({"Service": "web", "State": "running"}),
                json.dumps({"Service": "database", "State": "exited"}),
            ]
        )

        parsed_services = runtime_status.parse_compose_ps_output(raw_output)

        self.assertEqual(len(parsed_services), 2)
        self.assertEqual(parsed_services[0]["Service"], "web")

    def test_local_runtime_status_reports_not_selected_without_runtime_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            runtime_env_file = Path(temporary_directory_name) / "missing.env"

            payload = runtime_status.local_runtime_status(
                runtime_env_file,
                compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
                run_command_capture_fn=lambda _command: "[]",
            )

            self.assertEqual(payload["state"], "not_selected")
            self.assertEqual(payload["project_running"], False)

    def test_local_runtime_status_reports_compose_error(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            runtime_env_file = Path(temporary_directory_name) / "selected.env"
            runtime_env_file.write_text("PLATFORM_CONTEXT=cm\n", encoding="utf-8")

            payload = runtime_status.local_runtime_status(
                runtime_env_file,
                compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
                run_command_capture_fn=lambda _command: (_ for _ in ()).throw(click.ClickException("compose failed")),
            )

            self.assertEqual(payload["state"], "error")
            self.assertEqual(payload["compose_error"], "compose failed")

    def test_local_runtime_status_counts_running_services(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            runtime_env_file = Path(temporary_directory_name) / "selected.env"
            runtime_env_file.write_text("PLATFORM_CONTEXT=cm\n", encoding="utf-8")

            raw_payload = json.dumps(
                [
                    {
                        "Name": "project-web-1",
                        "Service": "web",
                        "State": "running",
                        "Status": "Up 5 seconds",
                        "Health": "healthy",
                        "ExitCode": 0,
                        "Publishers": [
                            {
                                "URL": "0.0.0.0",
                                "Protocol": "tcp",
                                "TargetPort": 8069,
                                "PublishedPort": 8069,
                            }
                        ],
                    },
                    {
                        "Name": "project-database-1",
                        "Service": "database",
                        "State": "exited",
                        "Status": "Exited",
                        "ExitCode": 0,
                    },
                ]
            )

            payload = runtime_status.local_runtime_status(
                runtime_env_file,
                compose_base_command_fn=lambda _runtime_env_file: ["docker", "compose"],
                run_command_capture_fn=lambda _command: raw_payload,
            )

            self.assertEqual(payload["state"], "running")
            self.assertEqual(payload["running_services"], 1)
            services = payload["services"]
            assert isinstance(services, list)
            first_service = services[0]
            assert isinstance(first_service, dict)
            self.assertEqual(first_service["service"], "web")


if __name__ == "__main__":
    unittest.main()
