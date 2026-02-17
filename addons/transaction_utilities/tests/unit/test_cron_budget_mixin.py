from odoo.addons.transaction_utilities.models import cron_budget_mixin

from ..common_imports import UNIT_TAGS, patch, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestCronBudgetMixin(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cron_budget_model = self.env["transaction.cron_budget.mixin"]

    def test_with_cron_runtime_budget_sets_deadline_context(self) -> None:
        with patch.object(cron_budget_mixin.config, "get", return_value=120):
            with patch.object(cron_budget_mixin, "monotonic", return_value=100.0):
                model_with_budget = self.cron_budget_model._with_cron_runtime_budget(job_name="Sample Import")

        self.assertEqual(
            model_with_budget.env.context.get(cron_budget_mixin.CRON_RUNTIME_BUDGET_SECONDS_CONTEXT_KEY),
            105,
        )
        self.assertEqual(
            model_with_budget.env.context.get(cron_budget_mixin.CRON_RUNTIME_LIMIT_SECONDS_CONTEXT_KEY),
            120,
        )
        self.assertEqual(
            model_with_budget.env.context.get(cron_budget_mixin.CRON_RUNTIME_DEADLINE_CONTEXT_KEY),
            205.0,
        )

    def test_with_cron_runtime_budget_skips_deadline_for_unlimited_runtime(self) -> None:
        with patch.object(cron_budget_mixin.config, "get", return_value=0):
            model_with_budget = self.cron_budget_model._with_cron_runtime_budget(job_name="Sample Import")

        self.assertEqual(model_with_budget, self.cron_budget_model)
        self.assertFalse(model_with_budget.env.context.get(cron_budget_mixin.CRON_RUNTIME_DEADLINE_CONTEXT_KEY))

    def test_is_cron_runtime_budget_exhausted(self) -> None:
        model_with_deadline = self.cron_budget_model.with_context(
            **{cron_budget_mixin.CRON_RUNTIME_DEADLINE_CONTEXT_KEY: 100.0}
        )
        with patch.object(cron_budget_mixin, "monotonic", return_value=101.0):
            self.assertTrue(model_with_deadline._is_cron_runtime_budget_exhausted())
        with patch.object(cron_budget_mixin, "monotonic", return_value=99.0):
            self.assertFalse(model_with_deadline._is_cron_runtime_budget_exhausted())

    def test_raise_if_cron_runtime_budget_exhausted(self) -> None:
        model_with_deadline = self.cron_budget_model.with_context(
            **{
                cron_budget_mixin.CRON_RUNTIME_DEADLINE_CONTEXT_KEY: 100.0,
                cron_budget_mixin.CRON_RUNTIME_BUDGET_SECONDS_CONTEXT_KEY: 90,
            }
        )

        with patch.object(cron_budget_mixin, "monotonic", return_value=101.0):
            with self.assertRaises(cron_budget_mixin.CronRuntimeBudgetExceeded) as raised_error:
                model_with_deadline._raise_if_cron_runtime_budget_exhausted(job_name="Sample Import")

        self.assertEqual(str(raised_error.exception), "Sample Import: paused after reaching runtime budget (90s)")

    def test_compute_cron_runtime_budget_seconds_respects_safety_margin(self) -> None:
        runtime_budget = self.cron_budget_model._compute_cron_runtime_budget_seconds(
            120,
            safety_margin_seconds=15,
            minimum_budget_seconds=20,
        )
        self.assertEqual(runtime_budget, 105)

    def test_compute_cron_runtime_budget_seconds_respects_minimum_budget(self) -> None:
        runtime_budget = self.cron_budget_model._compute_cron_runtime_budget_seconds(
            10,
            safety_margin_seconds=5,
            minimum_budget_seconds=20,
        )
        self.assertEqual(runtime_budget, 9)
