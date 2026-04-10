import importlib.util
from pathlib import Path
from types import ModuleType

from ... import hooks
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _load_base_pre_migration_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[3] / "openupgrade_scripts_custom" / "scripts" / "base" / "19.0.1.0" / "pre-migration.py"
    spec = importlib.util.spec_from_file_location("openupgrade_base_pre_migration", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load migration module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@common.tagged(*common.UNIT_TAGS)
class TestShopifyCronMigration(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config_parameter_model = self.env["ir.config_parameter"].sudo()
        self._clear_snapshot()
        self.dispatcher_cron = self.env.ref("shopify_sync.ir_cron_shopify_sync_dispatch")
        self.original_active = self.dispatcher_cron.active

    def tearDown(self) -> None:
        self._set_dispatcher_active(self.original_active)
        self._clear_snapshot()
        super().tearDown()

    def _clear_snapshot(self) -> None:
        self.config_parameter_model.search([("key", "=", hooks.SHOPIFY_DISPATCHER_CRON_SNAPSHOT_PARAMETER)]).unlink()

    def _cron_active(self) -> bool:
        return bool(self.env.ref("shopify_sync.ir_cron_shopify_sync_dispatch").active)

    def _set_dispatcher_active(self, active: bool) -> None:
        self.dispatcher_cron.sudo().write({"active": active})
        self.env["ir.cron"].flush_model(["active"])

    def test_snapshot_and_restore_preserves_active_dispatcher_cron(self) -> None:
        migration_module = _load_base_pre_migration_module()

        self._set_dispatcher_active(True)
        migration_module._snapshot_shopify_dispatcher_cron_active(self.env)

        self.assertEqual(
            self.config_parameter_model.get_param(hooks.SHOPIFY_DISPATCHER_CRON_SNAPSHOT_PARAMETER),
            "true",
        )

        self._set_dispatcher_active(False)
        hooks._restore_shopify_dispatcher_cron_active(self.env)

        self.assertTrue(self._cron_active())
        self.assertFalse(
            self.config_parameter_model.search_count([("key", "=", hooks.SHOPIFY_DISPATCHER_CRON_SNAPSHOT_PARAMETER)])
        )

    def test_snapshot_and_restore_preserves_inactive_dispatcher_cron(self) -> None:
        migration_module = _load_base_pre_migration_module()

        self._set_dispatcher_active(False)
        migration_module._snapshot_shopify_dispatcher_cron_active(self.env)

        self.assertEqual(
            self.config_parameter_model.get_param(hooks.SHOPIFY_DISPATCHER_CRON_SNAPSHOT_PARAMETER),
            "false",
        )

        self._set_dispatcher_active(True)
        hooks._restore_shopify_dispatcher_cron_active(self.env)

        self.assertFalse(self._cron_active())
        self.assertFalse(
            self.config_parameter_model.search_count([("key", "=", hooks.SHOPIFY_DISPATCHER_CRON_SNAPSHOT_PARAMETER)])
        )
