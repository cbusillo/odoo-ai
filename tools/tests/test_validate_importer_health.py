"""Regression tests for tracked importer health validation scenarios."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast
from unittest import mock

from tools.validate import importer_health


class ImporterHealthValidationTests(unittest.TestCase):
    def test_load_settings_prefers_scoped_base_url_from_environment(self) -> None:
        fake_environment_values = {
            "ODOO_DB_NAME": "cm-local-db",
            "ODOO_KEY": "secret-key",
            "ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL": "https://cm-local.shinycomputers.com",
        }

        with mock.patch.object(
            importer_health.platform_environment,
            "load_environment",
            return_value=(Path("/tmp/.env"), fake_environment_values),
        ):
            settings = importer_health.load_settings(
                repository_root=Path("/repo"),
                env_file=None,
                context_name="cm",
                instance_name="local",
                remote_login="gpt-admin",
            )

        self.assertEqual(settings.odoo_url, "https://cm-local.shinycomputers.com")
        self.assertEqual(settings.database_name, "cm-local-db")
        self.assertEqual(settings.odoo_password, "secret-key")

    def test_load_settings_falls_back_to_local_runtime_port(self) -> None:
        fake_environment_values = {
            "ODOO_DB_NAME": "cm-local-db",
            "ODOO_KEY": "secret-key",
        }
        runtime_selection = mock.Mock(web_host_port=8069)

        with (
            mock.patch.object(
                importer_health.platform_environment,
                "load_environment",
                return_value=(Path("/tmp/.env"), fake_environment_values),
            ),
            mock.patch.object(
                importer_health.platform_environment, "load_stack", return_value=mock.Mock(stack_definition=mock.sentinel.stack)
            ),
            mock.patch.object(importer_health.platform_runtime, "resolve_runtime_selection", return_value=runtime_selection),
        ):
            settings = importer_health.load_settings(
                repository_root=Path("/repo"),
                env_file=None,
                context_name="cm",
                instance_name="local",
                remote_login="gpt-admin",
            )

        self.assertEqual(settings.odoo_url, "http://127.0.0.1:8069")

    def test_collect_importer_snapshot_uses_cm_model_method(self) -> None:
        client = mock.Mock()
        client.execute.return_value = {"importer": "cm-data", "ok": True}

        result = importer_health.collect_importer_snapshot(client, "cm-data")

        self.assertEqual(result, {"importer": "cm-data", "ok": True})
        client.execute.assert_called_once_with("integration.cm_data.importer", "get_validation_health_snapshot", [])

    def test_run_validation_command_marks_failed_importers(self) -> None:
        fake_settings = importer_health.RemoteOdooSettings(
            odoo_url="https://cm-local.shinycomputers.com",
            database_name="cm",
            odoo_password="secret-key",
            remote_login="gpt-admin",
        )
        fake_client = mock.sentinel.client

        with (
            mock.patch.object(importer_health, "load_settings", return_value=fake_settings),
            mock.patch.object(importer_health, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(
                importer_health,
                "collect_importer_snapshot",
                side_effect=[
                    {"importer": "cm-data", "ok": True},
                    RuntimeError("resume state is dirty"),
                ],
            ),
        ):
            results = importer_health.run_validation_command(
                context_name="cm",
                instance_name="local",
                env_file=None,
                remote_login="gpt-admin",
                importers=("cm-data", "fishbowl"),
                repository_root=Path("/repo"),
            )
        importer_results = cast(dict[str, object], results["importers"])
        cm_data_results = cast(dict[str, object], importer_results["cm-data"])
        fishbowl_results = cast(dict[str, object], importer_results["fishbowl"])

        self.assertFalse(results["overall_ok"])
        self.assertEqual(results["failed_importers"], ["fishbowl"])
        self.assertEqual(cm_data_results["ok"], True)
        self.assertEqual(fishbowl_results["error"], "resume state is dirty")


if __name__ == "__main__":
    unittest.main()
