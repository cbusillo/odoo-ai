"""Regression tests for testkit session fanout controls."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tools.testkit.executor import ShardExecutionRequest
from tools.testkit.plan import ClassShardItem, PhaseExecutionPlan, PhaseName
from tools.testkit.session import TestSession


class TestkitSessionFanoutTests(unittest.TestCase):
    def test_tour_phase_uses_tour_max_procs_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TEST_MAX_PROCS": "4",
                "TOUR_MAX_PROCS": "1",
            },
            clear=True,
        ):
            session = TestSession()
            max_workers = session._resolve_phase_max_workers("tour", 5)
            self.assertEqual(max_workers, 1)

    def test_non_tour_phase_uses_global_max_procs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TEST_MAX_PROCS": "3",
                "TOUR_MAX_PROCS": "1",
            },
            clear=True,
        ):
            session = TestSession()
            max_workers = session._resolve_phase_max_workers("unit", 6)
            self.assertEqual(max_workers, 3)

    def test_unit_phase_auto_budget_uses_detected_cpu_count(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            session = TestSession()
            with patch.object(TestSession, "_detect_cpu_count", return_value=12):
                max_workers = session._resolve_phase_max_workers("unit", 20)
            self.assertEqual(max_workers, 12)

    def test_js_phase_auto_budget_stays_conservative(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            session = TestSession()
            with patch.object(TestSession, "_detect_cpu_count", return_value=16):
                max_workers = session._resolve_phase_max_workers("js", 10)
            self.assertEqual(max_workers, 2)

    def test_build_run_plan_uses_explicit_overlap_groups(self) -> None:
        phase_names: tuple[PhaseName, ...] = ("unit", "js", "integration", "tour")
        empty_phase_plans = [
            PhaseExecutionPlan(
                phase=phase,
                modules=(),
                timeout=1,
                strategy="empty",
                requested_shards=None,
                effective_shards=0,
                max_workers=0,
                template_strategy="none",
                uses_browser=False,
                uses_production_clone=False,
            )
            for phase in phase_names
        ]
        with patch.dict(os.environ, {"PHASES_OVERLAP": "1"}, clear=True):
            session = TestSession()
            with patch.object(session, "build_phase_plan", side_effect=empty_phase_plans):
                run_plan = session.build_run_plan()

        self.assertEqual(run_plan.phase_groups, (("unit", "js"), ("integration", "tour")))
        self.assertEqual(run_plan.browser_slots, 1)
        self.assertEqual(run_plan.production_clone_slots, 2)

    def test_browser_requests_respect_host_browser_slots(self) -> None:
        with patch.dict(os.environ, {"TESTKIT_BROWSER_SLOTS": "1"}, clear=True):
            session = TestSession()

        requests = [
            ShardExecutionRequest(test_tags="js_test", db_name="one", modules_to_install=("a",), timeout=60, is_js_test=True),
            ShardExecutionRequest(test_tags="js_test", db_name="two", modules_to_install=("b",), timeout=60, is_js_test=True),
        ]

        self.assertEqual(session._host_resource_limit_for_requests(requests), 1)
        self.assertEqual(session._effective_workers_for_requests("js", requests, max_workers=2), 1)

    def test_tour_requests_respect_both_browser_and_clone_slots(self) -> None:
        with patch.dict(
            os.environ,
            {"TESTKIT_BROWSER_SLOTS": "2", "TESTKIT_PRODUCTION_CLONE_SLOTS": "1"},
            clear=True,
        ):
            session = TestSession()

        requests = [
            ShardExecutionRequest(
                test_tags="tour_test",
                db_name="tour-one",
                modules_to_install=("website_sale",),
                timeout=60,
                is_tour_test=True,
                use_production_clone=True,
            ),
            ShardExecutionRequest(
                test_tags="tour_test",
                db_name="tour-two",
                modules_to_install=("website_sale",),
                timeout=60,
                is_tour_test=True,
                use_production_clone=True,
            ),
        ]

        self.assertEqual(session._host_resource_limit_for_requests(requests), 1)
        self.assertEqual(session._effective_workers_for_requests("tour", requests, max_workers=2), 1)

    def test_acquire_host_resources_for_request_releases_after_use(self) -> None:
        with patch.dict(os.environ, {"TESTKIT_BROWSER_SLOTS": "1"}, clear=True):
            session = TestSession()

        request = ShardExecutionRequest(
            test_tags="js_test",
            db_name="lease-test",
            modules_to_install=("shopify_sync",),
            timeout=60,
            is_js_test=True,
        )

        with session._acquire_host_resources_for_request(request):
            acquired = session._host_resource_semaphores["browser"].acquire(blocking=False)
            self.assertFalse(acquired)

        reacquired = session._host_resource_semaphores["browser"].acquire(blocking=False)
        self.assertTrue(reacquired)
        if reacquired:
            session._host_resource_semaphores["browser"].release()

    def test_discover_js_modules_uses_static_test_pattern(self) -> None:
        session = TestSession()
        with patch.object(session, "_manifest_modules", return_value=["shopify_sync"]) as manifest_modules_mock:
            modules = session._discover_js_modules()

        manifest_modules_mock.assert_called_once_with(patterns=["**/static/tests/**/*.test.js"])
        self.assertEqual(modules, ["shopify_sync"])

    def test_build_method_slice_requests_preserves_slice_metadata(self) -> None:
        session = TestSession()
        phase_plan = PhaseExecutionPlan(
            phase="unit",
            modules=("authentik_sso",),
            timeout=600,
            strategy="method_slicing",
            requested_shards=2,
            effective_shards=2,
            max_workers=2,
            template_strategy="phase",
            uses_browser=False,
            uses_production_clone=False,
            slice_count=2,
        )

        with patch.object(session, "_cap_by_db_guardrail", return_value=2), patch.object(
            session,
            "_template_db_for_phase",
            return_value="unit-template",
        ):
            requests = session._build_method_slice_requests(phase_plan)

        self.assertEqual(len(requests), 2)
        first_env = requests[0].extra_env
        second_env = requests[1].extra_env
        assert first_env is not None
        assert second_env is not None
        self.assertEqual(requests[0].db_name, "odoo_test_unit_m000")
        self.assertEqual(requests[1].db_name, "odoo_test_unit_m001")
        self.assertEqual(requests[0].shard_label, "ms000")
        self.assertEqual(first_env["TEST_SLICE_TOTAL"], "2")
        self.assertEqual(second_env["TEST_SLICE_INDEX"], "1")

    def test_build_module_shard_requests_keeps_single_shard_prefix_behavior(self) -> None:
        session = TestSession()
        phase_plan = PhaseExecutionPlan(
            phase="tour",
            modules=("website_sale",),
            timeout=1800,
            strategy="module_sharding",
            requested_shards=1,
            effective_shards=1,
            max_workers=1,
            template_strategy="production",
            uses_browser=True,
            uses_production_clone=True,
            module_shards=(("website_sale",),),
        )

        with patch.object(session, "_template_db_for_phase", return_value="prod-template"):
            requests = session._build_module_shard_requests(phase_plan)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].db_name, "odoo_test_tour")
        self.assertTrue(requests[0].use_module_prefix)
        self.assertEqual(requests[0].test_tags, "tour_test,-js_test")
        self.assertTrue(requests[0].use_production_clone)

    def test_build_class_shard_requests_scopes_tags_per_class(self) -> None:
        session = TestSession()
        phase_plan = PhaseExecutionPlan(
            phase="integration",
            modules=("authentik_sso",),
            timeout=900,
            strategy="class_sharding",
            requested_shards=1,
            effective_shards=1,
            max_workers=1,
            template_strategy="production",
            uses_browser=False,
            uses_production_clone=True,
            class_shards=((ClassShardItem(module="authentik_sso", class_name="TestSSO", weight=3),),),
        )

        with patch.object(session, "_template_db_for_phase", return_value="prod-template"):
            requests = session._build_class_shard_requests(phase_plan)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].test_tags, "integration_test/authentik_sso:TestSSO")
        self.assertEqual(requests[0].modules_to_install, ("authentik_sso",))
        self.assertTrue(requests[0].db_name.startswith("odoo_test_integration_"))


if __name__ == "__main__":
    unittest.main()
