"""Regression tests for tracked Shopify round-trip validation scenarios."""

from __future__ import annotations

import unittest
import xmlrpc.client
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
            1,
        ]

        sync_id = shopify_roundtrip.create_sync(client, "export_all_products")

        self.assertEqual(sync_id, 42)
        self.assertEqual(client.execute.call_args_list[0].args[0:2], ("shopify.sync", "create_and_run_async"))
        self.assertEqual(client.execute.call_args_list[1].args[0:2], ("shopify.sync", "search_read"))
        self.assertEqual(client.execute.call_args_list[2].args[0:2], ("shopify.sync", "dispatch_pending_syncs_for_validation"))

    def test_run_validation_command_forwards_start_after_export(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client

        with (
            mock.patch.object(shopify_roundtrip, "load_settings", return_value=fake_settings) as load_settings_mock,
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "pause_dispatcher_cron", return_value=True) as pause_dispatcher_cron_mock,
            mock.patch.object(shopify_roundtrip, "pause_sync_autoschedule", return_value=None) as pause_sync_autoschedule_mock,
            mock.patch.object(shopify_roundtrip, "pause_webhook_processing", return_value=None) as pause_webhook_processing_mock,
            mock.patch.object(shopify_roundtrip, "ensure_no_conflicting_syncs") as ensure_no_conflicting_syncs_mock,
            mock.patch.object(
                shopify_roundtrip,
                "read_validation_runtime_state",
                return_value={"active_syncs": [], "dispatcher_cron": {"active": True}, "autoschedule_pause": None, "webhook_pause": None},
            ),
            mock.patch.object(
                shopify_roundtrip,
                "run_roundtrip",
                return_value={"start_mode": "after_export"},
            ) as run_roundtrip_mock,
            mock.patch.object(shopify_roundtrip, "restore_sync_autoschedule") as restore_sync_autoschedule_mock,
            mock.patch.object(shopify_roundtrip, "restore_webhook_processing") as restore_webhook_processing_mock,
            mock.patch.object(shopify_roundtrip, "restore_dispatcher_cron") as restore_dispatcher_cron_mock,
        ):
            results = shopify_roundtrip.run_validation_command(
                context_name="opw",
                instance_name="testing",
                env_file=None,
                remote_login="gpt-admin",
                profile="smoke",
                sample_size=7,
                clear_conflicting_syncs=True,
                start_after_export=True,
                repository_root=Path("/repo"),
            )

        self.assertEqual(results["start_mode"], "after_export")
        self.assertIn("operator_summary", results)
        self.assertIn("post_validation_runtime_state", results)
        load_settings_mock.assert_called_once()
        pause_dispatcher_cron_mock.assert_called_once_with(fake_client)
        pause_sync_autoschedule_mock.assert_called_once_with(fake_client)
        pause_webhook_processing_mock.assert_called_once_with(fake_client)
        ensure_no_conflicting_syncs_mock.assert_called_once_with(fake_client, clear_conflicts=True)
        run_roundtrip_mock.assert_called_once_with(
            fake_settings,
            profile="smoke",
            sample_size=7,
            start_after_export=True,
            client=fake_client,
        )
        restore_sync_autoschedule_mock.assert_called_once_with(fake_client, original_value=None)
        restore_webhook_processing_mock.assert_called_once_with(fake_client, original_value=None)
        restore_dispatcher_cron_mock.assert_called_once_with(fake_client, originally_active=True)

    def test_run_validation_command_restores_dispatcher_on_failure(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client

        with (
            mock.patch.object(shopify_roundtrip, "load_settings", return_value=fake_settings),
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "pause_dispatcher_cron", return_value=False),
            mock.patch.object(shopify_roundtrip, "pause_sync_autoschedule", return_value=None),
            mock.patch.object(shopify_roundtrip, "pause_webhook_processing", return_value="1"),
            mock.patch.object(shopify_roundtrip, "ensure_no_conflicting_syncs"),
            mock.patch.object(shopify_roundtrip, "run_roundtrip", side_effect=RuntimeError("boom")),
            mock.patch.object(shopify_roundtrip, "restore_sync_autoschedule") as restore_sync_autoschedule_mock,
            mock.patch.object(shopify_roundtrip, "restore_webhook_processing") as restore_webhook_processing_mock,
            mock.patch.object(shopify_roundtrip, "restore_dispatcher_cron") as restore_dispatcher_cron_mock,
        ):
            with self.assertRaises(RuntimeError):
                shopify_roundtrip.run_validation_command(
                    context_name="opw",
                    instance_name="testing",
                    env_file=None,
                    remote_login="gpt-admin",
                    repository_root=Path("/repo"),
                )

        restore_sync_autoschedule_mock.assert_called_once_with(fake_client, original_value=None)
        restore_webhook_processing_mock.assert_called_once_with(fake_client, original_value="1")
        restore_dispatcher_cron_mock.assert_called_once_with(fake_client, originally_active=False)

    def test_run_validation_command_does_not_restore_unapplied_pause_state(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client

        with (
            mock.patch.object(shopify_roundtrip, "load_settings", return_value=fake_settings),
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "pause_dispatcher_cron", side_effect=RuntimeError("pause failed")),
            mock.patch.object(shopify_roundtrip, "restore_sync_autoschedule") as restore_sync_autoschedule_mock,
            mock.patch.object(shopify_roundtrip, "restore_webhook_processing") as restore_webhook_processing_mock,
            mock.patch.object(shopify_roundtrip, "restore_dispatcher_cron") as restore_dispatcher_cron_mock,
        ):
            with self.assertRaises(RuntimeError):
                shopify_roundtrip.run_validation_command(
                    context_name="opw",
                    instance_name="testing",
                    env_file=None,
                    remote_login="gpt-admin",
                    repository_root=Path("/repo"),
                )

        restore_sync_autoschedule_mock.assert_not_called()
        restore_webhook_processing_mock.assert_not_called()
        restore_dispatcher_cron_mock.assert_not_called()

    def test_ensure_no_conflicting_syncs_fails_fast_by_default(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "list_conflicting_syncs",
            return_value=[{"id": 42, "mode": "export_changed_products", "state": "running"}],
        ):
            with self.assertRaises(click.ClickException):
                shopify_roundtrip.ensure_no_conflicting_syncs(client, clear_conflicts=False)

        client.execute.assert_not_called()

    def test_ensure_no_conflicting_syncs_clears_when_explicitly_requested(self) -> None:
        client = mock.Mock()

        with (
            mock.patch.object(
                shopify_roundtrip,
                "list_conflicting_syncs",
                return_value=[{"id": 42, "mode": "export_changed_products", "state": "running"}],
            ),
            mock.patch.object(shopify_roundtrip, "clear_conflicting_syncs", return_value=[42]) as clear_conflicting_syncs_mock,
        ):
            shopify_roundtrip.ensure_no_conflicting_syncs(client, clear_conflicts=True)

        clear_conflicting_syncs_mock.assert_called_once_with(
            client,
            reason="Canceled before Shopify round-trip validation via --clear-conflicting-syncs",
        )

    def test_clear_conflicting_syncs_cancels_queued_and_requests_running(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "list_conflicting_syncs",
            return_value=[
                {"id": 41, "mode": "reset_shopify", "state": "queued"},
                {"id": 42, "mode": "export_changed_products", "state": "running"},
            ],
        ):
            cleared_sync_ids = shopify_roundtrip.clear_conflicting_syncs(client, reason="because")

        self.assertEqual(cleared_sync_ids, [41, 42])
        self.assertEqual(
            client.execute.call_args_list,
            [
                mock.call("shopify.sync", "write", [[41], {"state": "canceled", "error_message": "because"}]),
                mock.call("shopify.sync", "write", [[42], {"cancel_requested": True, "cancel_reason": "because"}]),
            ],
        )

    def test_pause_dispatcher_cron_disables_active_cron(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "read_dispatcher_cron",
            side_effect=[{"id": 101, "active": True}, {"id": 101, "active": True}, {"id": 101, "active": False}],
        ):
            was_active = shopify_roundtrip.pause_dispatcher_cron(client)

        self.assertTrue(was_active)
        client.execute.assert_called_once_with("ir.cron", "write", [[101], {"active": False}])

    def test_pause_dispatcher_cron_retries_busy_cron_write(self) -> None:
        client = mock.Mock()
        client.execute.side_effect = [
            xmlrpc.client.Fault(2, "Record cannot be modified right now: This cron task is currently being executed and may not be modified Please try again in a few minutes"),
            None,
        ]

        with (
            mock.patch.object(
                shopify_roundtrip,
                "read_dispatcher_cron",
                side_effect=[{"id": 101, "active": True}, {"id": 101, "active": True}, {"id": 101, "active": False}],
            ),
            mock.patch.object(shopify_roundtrip.time, "sleep") as sleep_mock,
        ):
            was_active = shopify_roundtrip.pause_dispatcher_cron(client)

        self.assertTrue(was_active)
        self.assertEqual(client.execute.call_count, 2)
        sleep_mock.assert_called_once_with(shopify_roundtrip.CRON_PAUSE_RETRY_SECONDS)

    def test_restore_dispatcher_cron_restores_original_state(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "read_dispatcher_cron",
            side_effect=[{"id": 101, "active": False}, {"id": 101, "active": True}],
        ):
            shopify_roundtrip.restore_dispatcher_cron(client, originally_active=True)

        client.execute.assert_called_once_with("ir.cron", "write", [[101], {"active": True}])

    def test_pause_webhook_processing_sets_flag_and_returns_original_value(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "read_config_parameter",
            side_effect=[None, None, {"id": 501, "key": shopify_roundtrip.SHOPIFY_WEBHOOK_PAUSE_KEY, "value": "1"}],
        ):
            original_value = shopify_roundtrip.pause_webhook_processing(client)

        self.assertIsNone(original_value)
        client.execute.assert_called_once_with(
            "ir.config_parameter",
            "create",
            [[{"key": shopify_roundtrip.SHOPIFY_WEBHOOK_PAUSE_KEY, "value": "1"}]],
        )

    def test_pause_sync_autoschedule_sets_flag_and_returns_original_value(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "read_config_parameter",
            side_effect=[None, None, {"id": 502, "key": shopify_roundtrip.SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": "1"}],
        ):
            original_value = shopify_roundtrip.pause_sync_autoschedule(client)

        self.assertIsNone(original_value)
        client.execute.assert_called_once_with(
            "ir.config_parameter",
            "create",
            [[{"key": shopify_roundtrip.SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": "1"}]],
        )

    def test_normalize_html_fragment_unescapes_entities(self) -> None:
        self.assertEqual(
            shopify_roundtrip._normalize_html_fragment("<p>Hello&nbsp;world</p>"),
            "<p>Hello\xa0world</p>",
        )

    def test_restore_webhook_processing_restores_original_value(self) -> None:
        client = mock.Mock()

        with mock.patch.object(
            shopify_roundtrip,
            "read_config_parameter",
            side_effect=[{"id": 501, "key": shopify_roundtrip.SHOPIFY_WEBHOOK_PAUSE_KEY, "value": "1"}, {"id": 501, "key": shopify_roundtrip.SHOPIFY_WEBHOOK_PAUSE_KEY, "value": "0"}],
        ):
            shopify_roundtrip.restore_webhook_processing(client, original_value="0")

        client.execute.assert_called_once_with(
            "ir.config_parameter",
            "write",
            [[501], {"value": "0"}],
        )

    def test_sample_product_ids_spreads_evenly(self) -> None:
        sampled_product_ids = shopify_roundtrip._sample_product_ids(list(range(1, 11)), sample_size=4)

        self.assertEqual(sampled_product_ids, (1, 4, 7, 10))

    def test_select_roundtrip_product_smoke_includes_primary_product_in_sample(self) -> None:
        fake_client = mock.sentinel.client
        product_snapshot = shopify_roundtrip.ProductSnapshot(
            product_id=11,
            title="Example",
            description_html="<p>Example</p>",
            condition_id=2,
            condition_code="used",
        )

        with (
            mock.patch.object(shopify_roundtrip, "_find_roundtrip_candidate", return_value=(product_snapshot, "shopify-11")),
            mock.patch.object(
                shopify_roundtrip,
                "search_export_candidates",
                return_value=[{"id": 20}, {"id": 30}, {"id": 40}],
            ),
        ):
            selection = shopify_roundtrip._select_roundtrip_product(fake_client, profile="smoke", sample_size=2)

        self.assertEqual(selection.product_snapshot.product_id, 11)
        self.assertEqual(selection.shopify_product_id, "shopify-11")
        self.assertEqual(selection.export_product_ids[0], 11)

    def test_run_roundtrip_smoke_uses_export_batch_products(self) -> None:
        fake_settings = mock.Mock(odoo_url="https://opw-testing.example.com")
        fake_client = mock.Mock()
        product_snapshot = shopify_roundtrip.ProductSnapshot(
            product_id=77,
            title="Example",
            description_html="<p>Example</p>",
            condition_id=5,
            condition_code="used",
        )
        selection = shopify_roundtrip.RoundtripProductSelection(
            product_snapshot=product_snapshot,
            shopify_product_id="old-product-id",
            export_product_ids=(77, 88, 99),
        )

        with (
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "_select_roundtrip_product", return_value=selection),
            mock.patch.object(shopify_roundtrip, "_current_utc_timestamp", return_value="2026-03-13 15:50:18"),
            mock.patch.object(shopify_roundtrip, "create_sync", side_effect=[101, 102, 103, 104, 105]) as create_sync_mock,
            mock.patch.object(
                shopify_roundtrip,
                "wait_for_sync",
                side_effect=[
                    {"id": 101, "total_count": 0},
                    {"id": 102, "total_count": 3},
                    {"id": 103, "total_count": 1},
                    {"id": 104, "total_count": 1},
                    {"id": 105, "total_count": 1},
                ],
            ),
            mock.patch.object(shopify_roundtrip, "get_external_system_id", return_value="new-product-id"),
            mock.patch.object(shopify_roundtrip, "wait_for_related_syncs_to_quiet"),
            mock.patch.object(
                shopify_roundtrip,
                "wait_for_shopify_snapshot",
                return_value=shopify_roundtrip.ShopifyProductSnapshot(
                    title="Example",
                    description_html="<p>Example</p>",
                    condition_metafield_id="condition-1",
                    condition_code="new",
                ),
            ),
            mock.patch.object(
                shopify_roundtrip,
                "wait_for_odoo_snapshot",
                return_value=shopify_roundtrip.ProductSnapshot(
                    product_id=77,
                    title="Example",
                    description_html="<p>Example</p>",
                    condition_id=5,
                    condition_code="used",
                ),
            ),
            mock.patch.object(shopify_roundtrip, "select_alternate_condition", return_value=(6, "new")),
            mock.patch.object(shopify_roundtrip, "update_shopify_product_snapshot"),
            mock.patch.object(
                shopify_roundtrip,
                "stamp_non_sample_products_as_exported_for_validation",
                return_value="2026-03-13 15:50:19",
            ) as stamp_products_mock,
            mock.patch.object(shopify_roundtrip, "ensure_no_conflicting_syncs") as ensure_no_conflicting_syncs_mock,
        ):
            results = shopify_roundtrip.run_roundtrip(fake_settings, profile="smoke", sample_size=3, start_after_export=False)

        self.assertEqual(results["profile"], "smoke")
        self.assertEqual(results["prepare_sync_mode"], "export_batch_products")
        self.assertEqual(results["export_sample_product_ids"], [77, 88, 99])
        self.assertEqual(
            create_sync_mock.call_args_list[1].args,
            (fake_client, "export_batch_products", {"odoo_products_to_sync": [[6, 0, [77, 88, 99]]]})
        )
        self.assertEqual(
            create_sync_mock.call_args_list[2].args,
            (fake_client, "export_batch_products", {"odoo_products_to_sync": [[6, 0, [77]]]})
        )
        self.assertEqual(
            create_sync_mock.call_args_list[4].args,
            (fake_client, "export_batch_products", {"odoo_products_to_sync": [[6, 0, [77]]]})
        )
        stamp_products_mock.assert_called_once_with(fake_client, keep_product_ids=(77, 88, 99))
        ensure_no_conflicting_syncs_mock.assert_called_once_with(fake_client, clear_conflicts=True)

    def test_inject_primary_product_id_preserves_sample_size(self) -> None:
        adjusted_product_ids = shopify_roundtrip._inject_primary_product_id((20, 30), primary_product_id=11, sample_size=2)

        self.assertEqual(adjusted_product_ids, (11, 20))

    def test_run_roundtrip_rechecks_same_product_external_id_after_prepare(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client
        product_snapshot = shopify_roundtrip.ProductSnapshot(
            product_id=77,
            title="Example",
            description_html="<p>Example</p>",
            condition_id=5,
            condition_code="used",
        )
        selection = shopify_roundtrip.RoundtripProductSelection(
            product_snapshot=product_snapshot,
            shopify_product_id="old-product-id",
            export_product_ids=(77,),
        )

        with (
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "_select_roundtrip_product", return_value=selection),
            mock.patch.object(
                shopify_roundtrip,
                "get_external_system_id",
                return_value="new-product-id",
            ) as get_external_system_id_mock,
            mock.patch.object(shopify_roundtrip, "create_sync", side_effect=[101, 102]),
            mock.patch.object(shopify_roundtrip, "wait_for_sync", side_effect=[{"id": 101}, {"id": 102}]),
            mock.patch.object(shopify_roundtrip, "wait_for_related_syncs_to_quiet"),
            mock.patch.object(
                shopify_roundtrip,
                "_run_roundtrip_for_product",
                return_value={"shopify_product_id": "new-product-id"},
            ) as run_for_product_mock,
        ):
            results = shopify_roundtrip.run_roundtrip(fake_settings, profile="full", sample_size=shopify_roundtrip.DEFAULT_SAMPLE_SIZE, start_after_export=False)

        self.assertEqual(results["shopify_product_id"], "new-product-id")
        self.assertEqual(get_external_system_id_mock.call_count, 1)
        run_for_product_mock.assert_called_once_with(
            fake_client,
            fake_settings,
            product_snapshot=product_snapshot,
            shopify_product_id="new-product-id",
            profile="full",
        )

    def test_run_validation_command_rejects_sample_size_for_full_profile(self) -> None:
        with self.assertRaises(click.ClickException):
            shopify_roundtrip.run_validation_command(
                context_name="opw",
                instance_name="testing",
                env_file=None,
                remote_login="gpt-admin",
                profile="full",
                sample_size=5,
                repository_root=Path("/repo"),
            )

    def test_run_validation_command_rejects_shopify_roundtrip_on_prod(self) -> None:
        with self.assertRaises(click.ClickException):
            shopify_roundtrip.run_validation_command(
                context_name="opw",
                instance_name="prod",
                env_file=None,
                remote_login="gpt-admin",
                profile="full",
                sample_size=shopify_roundtrip.DEFAULT_SAMPLE_SIZE,
                repository_root=Path("/repo"),
            )

    def test_stamp_non_sample_products_for_validation_excludes_keep_ids_and_uses_future_timestamp(self) -> None:
        client = mock.Mock()
        client.execute.side_effect = [[2, 3], None]

        with mock.patch.object(
            shopify_roundtrip,
            "_future_utc_timestamp",
            return_value="2026-03-13 16:50:18",
        ):
            stamp_timestamp = shopify_roundtrip.stamp_non_sample_products_as_exported_for_validation(
                client,
                keep_product_ids=(1, 4),
            )

        self.assertEqual(stamp_timestamp, "2026-03-13 16:50:18")
        self.assertEqual(
            client.execute.call_args_list,
            [
                mock.call(
                    "product.product",
                    "search",
                    [[
                        ["sale_ok", "=", True],
                        ["is_ready_for_sale", "=", True],
                        ["is_published", "=", True],
                        ["website_description", "!=", False],
                        ["website_description", "!=", ""],
                        ["type", "=", "consu"],
                        ["id", "not in", [1, 4]],
                    ]],
                ),
                mock.call(
                    "product.product",
                    "write",
                    [[2, 3], {"shopify_last_exported_at": "2026-03-13 16:50:18", "shopify_next_export": False}],
                ),
            ],
        )

    def test_wait_for_related_syncs_to_quiet_ignores_canceled_syncs(self) -> None:
        client = mock.Mock()
        client.execute.return_value = [
            {
                "id": 99,
                "mode": "export_changed_products",
                "state": "canceled",
                "create_date": "2026-03-13 15:00:00",
                "write_date": "2026-03-13 15:00:00",
                "error_message": False,
            }
        ]

        class _FrozenDateTime(shopify_roundtrip.datetime):
            @classmethod
            def now(cls, tz: object = None):
                return shopify_roundtrip.datetime(2026, 3, 13, 15, 0, 20, tzinfo=shopify_roundtrip.UTC)

        with mock.patch.object(shopify_roundtrip, "datetime", _FrozenDateTime):
            rows = shopify_roundtrip.wait_for_related_syncs_to_quiet(
                client,
                since_timestamp="2026-03-13 15:00:00",
                modes=shopify_roundtrip.PREPARE_SYNC_MODES,
                label="quiet test",
            )

        self.assertEqual(len(rows), 1)

    def test_run_roundtrip_waits_for_prepare_related_syncs_to_quiet(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client
        product_snapshot = shopify_roundtrip.ProductSnapshot(
            product_id=77,
            title="Example",
            description_html="<p>Example</p>",
            condition_id=5,
            condition_code="used",
        )
        selection = shopify_roundtrip.RoundtripProductSelection(
            product_snapshot=product_snapshot,
            shopify_product_id="old-product-id",
            export_product_ids=(77,),
        )

        with (
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "_select_roundtrip_product", return_value=selection),
            mock.patch.object(shopify_roundtrip, "_current_utc_timestamp", return_value="2026-03-13 15:50:18"),
            mock.patch.object(shopify_roundtrip, "create_sync", side_effect=[101, 102]),
            mock.patch.object(shopify_roundtrip, "wait_for_sync", side_effect=[{"id": 101}, {"id": 102}]),
            mock.patch.object(shopify_roundtrip, "get_external_system_id", return_value="new-product-id"),
            mock.patch.object(shopify_roundtrip, "wait_for_related_syncs_to_quiet") as wait_for_related_syncs_to_quiet_mock,
            mock.patch.object(shopify_roundtrip, "_run_roundtrip_for_product", return_value={"shopify_product_id": "new-product-id"}),
        ):
            results = shopify_roundtrip.run_roundtrip(fake_settings, profile="full", sample_size=shopify_roundtrip.DEFAULT_SAMPLE_SIZE, start_after_export=False)

        self.assertEqual(results["start_mode"], "prepared")
        wait_for_related_syncs_to_quiet_mock.assert_called_once_with(
            fake_client,
            since_timestamp="2026-03-13 15:50:18",
            modes=shopify_roundtrip.PREPARE_SYNC_MODES,
            label="post prepare settle",
        )

    def test_run_roundtrip_resume_mode_skips_prepare_and_marks_start_mode(self) -> None:
        fake_settings = mock.sentinel.settings
        fake_client = mock.sentinel.client
        product_snapshot = shopify_roundtrip.ProductSnapshot(
            product_id=77,
            title="Example",
            description_html="<p>Example</p>",
            condition_id=5,
            condition_code="used",
        )
        selection = shopify_roundtrip.RoundtripProductSelection(
            product_snapshot=product_snapshot,
            shopify_product_id="product-id",
            export_product_ids=(77,),
        )

        with (
            mock.patch.object(shopify_roundtrip, "RemoteOdooClient", return_value=fake_client),
            mock.patch.object(shopify_roundtrip, "_select_roundtrip_product", return_value=selection),
            mock.patch.object(
                shopify_roundtrip,
                "_run_roundtrip_for_product",
                return_value={"shopify_product_id": "product-id"},
            ) as run_roundtrip_for_product_mock,
        ):
            results = shopify_roundtrip.run_roundtrip(fake_settings, profile="smoke", sample_size=3, start_after_export=True)

        self.assertEqual(results["start_mode"], "after_export")
        self.assertEqual(results["profile"], "smoke")
        run_roundtrip_for_product_mock.assert_called_once_with(
            fake_client,
            fake_settings,
            product_snapshot=product_snapshot,
            shopify_product_id="product-id",
            profile="smoke",
        )


if __name__ == "__main__":
    unittest.main()
