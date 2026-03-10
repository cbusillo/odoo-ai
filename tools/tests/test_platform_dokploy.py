"""Regression tests for extracted Dokploy helper logic."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import click
import requests

from tools.platform import dokploy
from tools.platform.models import DokployTargetDefinition, JsonValue


class PlatformDokployHelpersTests(unittest.TestCase):
    def test_resolve_ship_healthcheck_urls_normalizes_domain_and_path(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            domains=("cm-testing.shinycomputers.com",),
            healthcheck_path="web/health",
        )

        urls = dokploy.resolve_ship_healthcheck_urls(
            target_definition=target_definition,
            environment_values={},
        )

        self.assertEqual(urls, ("https://cm-testing.shinycomputers.com/web/health",))

    def test_resolve_ship_healthcheck_urls_respects_disabled_flag(self) -> None:
        target_definition = DokployTargetDefinition(
            context="cm",
            instance="testing",
            healthcheck_enabled=False,
            domains=("cm-testing.shinycomputers.com",),
        )

        urls = dokploy.resolve_ship_healthcheck_urls(
            target_definition=target_definition,
            environment_values={},
        )

        self.assertEqual(urls, ())

    def test_parse_and_serialize_dokploy_env_text(self) -> None:
        env_text = "# comment\nexport FOO=bar\nBAZ=qux\n"
        parsed_values = dokploy.parse_dokploy_env_text(env_text)

        self.assertEqual(parsed_values, {"FOO": "bar", "BAZ": "qux"})
        self.assertEqual(dokploy.serialize_dokploy_env_text(parsed_values), "FOO=bar\nBAZ=qux")

    def test_collect_rollback_ids_handles_nested_payload(self) -> None:
        payload: JsonValue = {
            "items": [
                {"rollbackId": "101"},
                {"rollback": {"id": "202"}},
                {"rollback_id": "303"},
            ]
        }

        rollback_ids = dokploy.collect_rollback_ids(payload)

        self.assertEqual(rollback_ids, ["101", "202", "303"])

    def test_resolve_dokploy_ship_mode_rejects_invalid_mode(self) -> None:
        with self.assertRaises(click.ClickException):
            dokploy.resolve_dokploy_ship_mode(
                context_name="cm",
                instance_name="testing",
                environment_values={"DOKPLOY_SHIP_MODE": "invalid"},
            )

    def test_dokploy_request_wraps_network_errors(self) -> None:
        with patch("tools.platform.dokploy.requests.request", side_effect=requests.RequestException("network down")):
            with self.assertRaises(click.ClickException):
                dokploy.dokploy_request(
                    host="https://dokploy.example",
                    token="token",
                    path="/api/health",
                )

    def test_collect_dokploy_deploy_servers_accepts_wrapped_payload(self) -> None:
        wrapped_payload: JsonValue = {
            "data": [
                {"serverId": "deploy-1", "name": "docker-cm-prod", "serverType": "deploy"},
                {"serverId": "build-1", "name": "builder-1", "serverType": "build"},
            ]
        }

        with patch("tools.platform.dokploy.dokploy_request", return_value=wrapped_payload):
            deploy_servers = dokploy.collect_dokploy_deploy_servers(
                host="https://dokploy.example",
                token="token",
            )

        self.assertEqual(deploy_servers, ({"serverId": "deploy-1", "name": "docker-cm-prod", "serverType": "deploy"},))

    def test_resolve_dokploy_target_prefers_source_of_truth_target_id(self) -> None:
        target_definition = DokployTargetDefinition(context="cm", instance="testing", target_id="compose-123",
                                                    target_name="cm-testing-compose")

        resolved_target = dokploy.resolve_dokploy_target(
            host="https://dokploy.example",
            token="token",
            context_name="cm",
            instance_name="testing",
            environment_values={},
            ship_mode="auto",
            target_definition=target_definition,
        )

        self.assertEqual(resolved_target, ("compose", "compose-123", "cm-testing-compose", None, None))

    def test_resolve_dokploy_target_rejects_conflicting_target_type_override(self) -> None:
        target_definition = DokployTargetDefinition(context="cm", instance="testing", target_id="compose-123")

        with self.assertRaises(click.ClickException):
            dokploy.resolve_dokploy_target(
                host="https://dokploy.example",
                token="token",
                context_name="cm",
                instance_name="testing",
                environment_values={},
                ship_mode="application",
                target_definition=target_definition,
            )

    def test_dokploy_status_payload_prefers_source_of_truth_target_id(self) -> None:
        target_definition = DokployTargetDefinition(context="cm", instance="testing", target_id="compose-123",
                                                    target_name="cm-testing-compose")

        def fake_request(**kwargs: object) -> JsonValue:
            self.assertEqual(kwargs.get("path"), "/api/compose.one")
            self.assertEqual(kwargs.get("query"), {"composeId": "compose-123"})
            return {
                "composeStatus": "running",
                "sourceType": "git",
                "serverId": "server-1",
                "appName": "odoo-cm-testing",
            }

        with (
            patch("tools.platform.dokploy.read_dokploy_config", return_value=("https://dokploy.example", "token")),
            patch("tools.platform.dokploy.dokploy_request", side_effect=fake_request),
            patch("tools.platform.dokploy.latest_deployment_for_compose", return_value={"id": "deploy-1", "status": "done"}),
        ):
            payload = dokploy.dokploy_status_payload(
                context_name="cm",
                instance_name="testing",
                environment_values={},
                target_definition=target_definition,
            )

        self.assertEqual(payload["target_type"], "compose")
        self.assertEqual(payload["target_id"], "compose-123")
        self.assertEqual(payload["target_name"], "cm-testing-compose")
        self.assertEqual(payload["server_id"], "server-1")

    def test_resolve_dokploy_target_for_command_prefers_source_of_truth_target_id(self) -> None:
        target_definition = DokployTargetDefinition(context="cm", instance="testing", target_id="compose-123",
                                                    target_name="cm-testing-compose")

        resolved_target = dokploy.resolve_dokploy_target_for_command(
            host="https://dokploy.example",
            token="token",
            context_name="cm",
            instance_name="testing",
            environment_values={},
            target_type="compose",
            target_definition=target_definition,
        )

        self.assertEqual(resolved_target, ("compose", "compose-123", "cm-testing-compose"))

    def test_update_dokploy_target_env_preserves_application_build_fields_when_strings(self) -> None:
        with patch("tools.platform.dokploy.dokploy_request") as request_mock:
            dokploy.update_dokploy_target_env(
                host="https://dokploy.example",
                token="token",
                target_type="application",
                target_id="app-123",
                target_payload={
                    "buildArgs": "A=1",
                    "buildSecrets": "SECRET=1",
                    "createEnvFile": False,
                },
                env_text="KEY=value",
            )

        payload = request_mock.call_args.kwargs["payload"]
        self.assertEqual(payload["applicationId"], "app-123")
        self.assertEqual(payload["env"], "KEY=value")
        self.assertEqual(payload["buildArgs"], "A=1")
        self.assertEqual(payload["buildSecrets"], "SECRET=1")
        self.assertEqual(payload["createEnvFile"], False)

    def test_update_dokploy_target_env_omits_non_string_application_build_fields(self) -> None:
        with patch("tools.platform.dokploy.dokploy_request") as request_mock:
            dokploy.update_dokploy_target_env(
                host="https://dokploy.example",
                token="token",
                target_type="application",
                target_id="app-123",
                target_payload={
                    "buildArgs": ["A=1"],
                    "buildSecrets": {"SECRET": "1"},
                },
                env_text="KEY=value",
            )

        payload = request_mock.call_args.kwargs["payload"]
        self.assertEqual(payload["applicationId"], "app-123")
        self.assertEqual(payload["env"], "KEY=value")
        self.assertNotIn("buildArgs", payload)
        self.assertNotIn("buildSecrets", payload)
        self.assertEqual(payload["createEnvFile"], True)


if __name__ == "__main__":
    unittest.main()
