import logging
from time import monotonic
from typing import Self

from odoo import models
from odoo.tools import config

_logger = logging.getLogger(__name__)

CRON_RUNTIME_DEADLINE_CONTEXT_KEY = "cron_runtime_deadline_monotonic"
CRON_RUNTIME_BUDGET_SECONDS_CONTEXT_KEY = "cron_runtime_budget_seconds"
CRON_RUNTIME_LIMIT_SECONDS_CONTEXT_KEY = "cron_runtime_limit_seconds"

DEFAULT_CRON_RUNTIME_LIMIT_SECONDS = 120
DEFAULT_CRON_RUNTIME_SAFETY_MARGIN_SECONDS = 15
DEFAULT_CRON_RUNTIME_MINIMUM_BUDGET_SECONDS = 20


class CronRuntimeBudgetExceeded(RuntimeError):
    """Raised when the current cron run reaches its runtime budget."""


class CronBudgetMixin(models.AbstractModel):
    _name = "transaction.cron_budget.mixin"
    _description = "Cron runtime budget helpers"

    def _with_cron_runtime_budget(
        self,
        *,
        job_name: str,
        safety_margin_seconds: int = DEFAULT_CRON_RUNTIME_SAFETY_MARGIN_SECONDS,
        minimum_budget_seconds: int = DEFAULT_CRON_RUNTIME_MINIMUM_BUDGET_SECONDS,
    ) -> Self:
        runtime_limit_seconds = self._get_cron_runtime_limit_seconds()
        if runtime_limit_seconds is None:
            return self
        runtime_budget_seconds = self._compute_cron_runtime_budget_seconds(
            runtime_limit_seconds,
            safety_margin_seconds=safety_margin_seconds,
            minimum_budget_seconds=minimum_budget_seconds,
        )
        deadline_monotonic = monotonic() + runtime_budget_seconds
        _logger.info(
            "%s: runtime budget %ss (limit %ss, safety margin %ss)",
            job_name,
            runtime_budget_seconds,
            runtime_limit_seconds,
            safety_margin_seconds,
        )
        return self.with_context(
            **{
                CRON_RUNTIME_DEADLINE_CONTEXT_KEY: deadline_monotonic,
                CRON_RUNTIME_BUDGET_SECONDS_CONTEXT_KEY: runtime_budget_seconds,
                CRON_RUNTIME_LIMIT_SECONDS_CONTEXT_KEY: runtime_limit_seconds,
            }
        )

    def _raise_if_cron_runtime_budget_exhausted(self, *, job_name: str) -> None:
        if not self._is_cron_runtime_budget_exhausted():
            return
        runtime_budget_seconds = self.env.context.get(CRON_RUNTIME_BUDGET_SECONDS_CONTEXT_KEY)
        if runtime_budget_seconds:
            raise CronRuntimeBudgetExceeded(f"{job_name}: paused after reaching runtime budget ({runtime_budget_seconds}s)")
        raise CronRuntimeBudgetExceeded(f"{job_name}: paused after reaching runtime budget")

    def _is_cron_runtime_budget_exhausted(self) -> bool:
        deadline_monotonic = self.env.context.get(CRON_RUNTIME_DEADLINE_CONTEXT_KEY)
        if not deadline_monotonic:
            return False
        try:
            return monotonic() >= float(deadline_monotonic)
        except (TypeError, ValueError):
            return False

    def _get_cron_runtime_limit_seconds(self) -> int | None:
        limit_time_real_cron = config.get("limit_time_real_cron")
        if limit_time_real_cron is None:
            return DEFAULT_CRON_RUNTIME_LIMIT_SECONDS
        runtime_limit_seconds = self._to_int_or_none(limit_time_real_cron)
        if runtime_limit_seconds is None:
            return DEFAULT_CRON_RUNTIME_LIMIT_SECONDS
        if runtime_limit_seconds <= 0:
            return None
        return runtime_limit_seconds

    @staticmethod
    def _compute_cron_runtime_budget_seconds(
        runtime_limit_seconds: int,
        *,
        safety_margin_seconds: int,
        minimum_budget_seconds: int,
    ) -> int:
        safety_margin = max(0, safety_margin_seconds)
        minimum_budget = max(1, minimum_budget_seconds)
        runtime_budget_seconds = runtime_limit_seconds - safety_margin
        runtime_budget_seconds = max(runtime_budget_seconds, minimum_budget)
        if runtime_budget_seconds >= runtime_limit_seconds:
            return max(1, runtime_limit_seconds - 1)
        return runtime_budget_seconds

    @staticmethod
    def _to_int_or_none(value: object) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None
