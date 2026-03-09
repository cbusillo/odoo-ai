from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PhaseName = Literal["unit", "js", "integration", "tour"]
TemplateStrategy = Literal["none", "phase", "production"]


@dataclass(frozen=True)
class ClassShardItem:
    module: str
    class_name: str
    weight: int

    def to_payload(self) -> dict[str, object]:
        return {
            "module": self.module,
            "class": self.class_name,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class PhaseExecutionPlan:
    phase: PhaseName
    modules: tuple[str, ...]
    timeout: int
    strategy: str
    requested_shards: int | None
    effective_shards: int
    max_workers: int
    template_strategy: TemplateStrategy
    uses_browser: bool
    uses_production_clone: bool
    auto_selected: int | None = None
    module_cap: int | None = None
    db_guarded: int | None = None
    total_weight: int | None = None
    module_shards: tuple[tuple[str, ...], ...] = ()
    class_shards: tuple[tuple[ClassShardItem, ...], ...] = ()
    slice_count: int = 0

    @property
    def is_empty(self) -> bool:
        return self.effective_shards == 0 or not self.modules

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "phase": self.phase,
            "strategy": self.strategy,
            "modules": len(self.modules),
            "module_names": list(self.modules),
            "timeout": self.timeout,
            "requested": self.requested_shards,
            "effective": self.effective_shards,
            "shards_count": self.effective_shards,
            "max_workers": self.max_workers,
            "template_strategy": self.template_strategy,
            "uses_browser": self.uses_browser,
            "uses_production_clone": self.uses_production_clone,
        }
        if self.auto_selected is not None:
            payload["auto_selected"] = self.auto_selected
        if self.module_cap is not None:
            payload["module_cap"] = self.module_cap
        if self.db_guarded is not None:
            payload["db_guarded"] = self.db_guarded
        if self.total_weight is not None:
            payload["total_weight"] = self.total_weight
        if self.module_shards:
            payload["shards"] = [list(shard) for shard in self.module_shards]
        elif self.class_shards:
            payload["shards"] = [[class_item.to_payload() for class_item in shard] for shard in self.class_shards]
        else:
            payload["shards"] = []
        if self.slice_count:
            payload["slice_count"] = self.slice_count
        return payload


@dataclass(frozen=True)
class RunExecutionPlan:
    phases: tuple[PhaseExecutionPlan, ...]
    phase_groups: tuple[tuple[PhaseName, ...], ...]
    overlap_enabled: bool
    browser_slots: int
    production_clone_slots: int
    schema: str = field(default="run-plan.v1")

    def phase(self, phase_name: PhaseName) -> PhaseExecutionPlan:
        for phase_plan in self.phases:
            if phase_plan.phase == phase_name:
                return phase_plan
        raise KeyError(phase_name)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "overlap_enabled": self.overlap_enabled,
            "host_resources": {
                "browser_slots": self.browser_slots,
                "production_clone_slots": self.production_clone_slots,
            },
            "phase_groups": [list(phase_group) for phase_group in self.phase_groups],
            "phases": {phase_plan.phase: phase_plan.to_payload() for phase_plan in self.phases},
        }
