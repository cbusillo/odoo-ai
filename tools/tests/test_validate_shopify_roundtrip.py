"""Regression tests for tracked Shopify round-trip validation scenarios."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import click

from tools.validate import shopify_roundtrip


class ShopifyRoundtripValidationTests(unittest.TestCase):
    def test_load_settings_reads_scoped_environment_values(self) -> None:
        fake_environment_values = {
            "ODOO_DB_NAME": "custom-opw-db",
            "ODOO_KEY": "secret-key",
            "ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY": "test-store",
            "ENV_OVERRIDE_SHOPIFY__API_TOKEN": "token-123",
            "ENV_OVERRIDE_SHOPIFY__API_VERSION": "2026-01",
        }

        with (
            mock.patch.object(shopify_roundtrip, "load_environment", return_value=(Path("/tmp/.env"), fake_environment_values)),
            mock.patch.object(shopify_roundtrip, "load_dokploy_source_of_truth", return_value=mock.sentinel.source_of_truth),
            mock.patch.object(shopify_roundtrip.platform_dokploy, "find_dokploy_target_definition", return_value=mock.sentinel.target),
            mock.patch.object(
                shopify_roundtrip.platform_dokploy,
                "resolve_healthcheck_base_urls",
                return_value=("https://opw-testing.example.com",),
            ),
        ):
            settings = shopify_roundtrip.load_settings(
                repository_root=Path("/repo"),
                env_file=None,
                context_name="opw",
                instance_name="testing",
                remote_login="gpt-admin",
            )

        self.assertEqual(settings.odoo_url, "https://opw-testing.example.com")
        self.assertEqual(settings.database_name, "custom-opw-db")
        self.assertEqual(settings.odoo_password, "secret-key")
        self.assertEqual(settings.remote_login, "gpt-admin")
        self.assertEqual(settings.shop_url_key, "test-store")
        self.assertEqual(settings.shopify_api_token, "token-123")
        self.assertEqual(settings.shopify_api_version, "2026-01")

    def test_load_settings_rejects_local_instance(self) -> None:
        with self.assertRaises(click.ClickException):
            shopify_roundtrip.load_settings(
                repository_root=Path("/repo"),
                env_file=None,
                context_name="opw",
                instance_name="local",
                remote_login="gpt-admin",
            )

    def test_create_sync_falls_back_to_existing_running_sync(self) -> None:
        client = mock.Mock()
        client.uid = 99
        client.execute.side_effect = [
            {"unexpected": True},
            [{"id": 42}],
        ]

        sync_id = shopify_roundtrip.create_sync(client, "export_all_products")

        self.assertEqual(sync_id, 42)
        self.assertEqual(client.execute.call_args_list[0].args[0:2], ("shopify.sync", "create_and_run_async"))
        self.assertEqual(client.execute.call_args_list[1].args[0:2], ("shopify.sync", "search_read"))


if __name__ == "__main__":
    unittest.main()
