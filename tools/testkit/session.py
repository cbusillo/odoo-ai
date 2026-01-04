import json
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Literal, TypeVar
from pathlib import Path

from .db import cleanup_test_databases, create_template_from_production, get_production_db_name
from .filestore import cleanup_filestores
from .phases import PhaseOutcome
from .reporter import (
    aggregate_phase,
    begin_session_dir,
    prune_old_sessions,
    update_latest_symlink,
    write_junit_for_phase,
    write_digest,
    write_latest_json,
    write_manifest,
    write_session_index,
)
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings
from .sharding import discover_modules_with, greedy_shards, plan_shards_for_phase

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")
PhaseName = Literal["unit", "js", "integration", "tour"]


def _log_suppressed(action: str, exc: Exception) -> None:
    _logger.debug("testkit session: %s failed (%s)", action, exc)


def _load_timeouts() -> dict:
    try:
        import tomllib  # Python 3.11+

        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return data.get("tool", {}).get("odoo-test", {}).get("timeouts", {}) or {}
    except (OSError, ValueError):
        return {}


class TestSession:
    def __init__(
        self,
        keep_going: bool | None = None,
        *,
        include_modules: list[str] | set[str] | None = None,
        exclude_modules: list[str] | set[str] | None = None,
        unit_modules: list[str] | set[str] | None = None,
        unit_exclude: list[str] | set[str] | None = None,
        js_modules: list[str] | set[str] | None = None,
        js_exclude: list[str] | set[str] | None = None,
        integration_modules: list[str] | set[str] | None = None,
        integration_exclude: list[str] | set[str] | None = None,
        tour_modules: list[str] | set[str] | None = None,
        tour_exclude: list[str] | set[str] | None = None,
    ) -> None:
        self.settings = TestSettings()
        self.keep_going = self.settings.test_keep_going if keep_going is None else keep_going
        self.session_dir: Path | None = None
        self.session_name: str | None = None
        self.session_started: float = 0.0
        self._include = set(include_modules or [])
        self._exclude = set(exclude_modules or [])
        self._p_include = {
            "unit": set(unit_modules or []),
            "js": set(js_modules or []),
            "integration": set(integration_modules or []),
            "tour": set(tour_modules or []),
        }
        self._p_exclude = {
            "unit": set(unit_exclude or []),
            "js": set(js_exclude or []),
            "integration": set(integration_exclude or []),
            "tour": set(tour_exclude or []),
        }
        self._template_db: str | None = None

    def start(self) -> None:
        self._begin()

    def finish(self, outcomes: dict[str, PhaseOutcome]) -> int:
        return self._finish(outcomes)

    def discover_modules(self, phase: PhaseName) -> list[str]:
        try:
            discover = {
                "unit": self._discover_unit_modules,
                "js": self._discover_js_modules,
                "integration": self._discover_integration_modules,
                "tour": self._discover_tour_modules,
            }[phase]
        except KeyError as exc:
            raise ValueError(f"Unknown phase {phase}") from exc
        return discover()

    def run_phase(self, phase: PhaseName, modules: list[str], timeout: int) -> PhaseOutcome:
        if phase == "unit":
            return self._run_unit_sharded(modules, timeout)
        if phase == "js":
            return self._run_js_sharded(modules, timeout)
        if phase == "integration":
            return self._run_integration_sharded(modules, timeout)
        if phase == "tour":
            return self._run_tour_sharded(modules, timeout)
        raise ValueError(f"Unknown phase {phase}")

    def _begin(self) -> None:
        self.session_dir, self.session_name, self.session_started = begin_session_dir()
        os.environ["TEST_LOG_SESSION"] = self.session_name or ""
        # Events stream
        from .events import EventStream

        self._events = EventStream((self.session_dir / "events.ndjson"), echo=self.settings.events_stdout)
        self._emit_event("session_started", session=self.session_name)
        # prune older sessions
        prune_old_sessions(Path("tmp/test-logs"), max(1, int(self.settings.test_log_keep)))
        # in-progress pointer
        try:
            cur = Path("tmp/test-logs") / "current"
            try:
                if cur.exists() or cur.is_symlink():
                    cur.unlink()
            except OSError as exc:
                _log_suppressed("unlink current", exc)
            rel = os.path.relpath(self.session_dir, cur.parent)
            try:
                cur.symlink_to(rel)
            except OSError:
                (cur.with_suffix(".json")).write_text(
                    json.dumps({"schema_version": SUMMARY_SCHEMA_VERSION, "current": str(self.session_dir)}, indent=2)
                )
        except OSError as exc:
            _log_suppressed("write current pointer", exc)

    def _emit_event(self, event: str, **payload: object) -> None:
        try:
            self._events.emit(event, **payload)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            _log_suppressed(f"emit {event}", exc)

    def _finish(self, outcomes: dict[str, PhaseOutcome]) -> int:
        assert self.session_dir and self.session_name
        any_fail = any(outcome.return_code not in (None, 0) for outcome in outcomes.values())

        # Source counts (definition counts)
        def _count_py(glob_pattern: str) -> int:
            total = 0
            for path in Path("addons").glob(glob_pattern):
                if path.is_file() and path.suffix == ".py":
                    try:
                        content = path.read_text(errors="ignore")
                        total += len(re.findall(r"^\s*def\s+test_", content, flags=re.MULTILINE))
                    except OSError as err:
                        _log_suppressed("read test file", err)
            return total

        def _count_js() -> int:
            total = 0
            for path in Path("addons").rglob("*.test.js"):
                try:
                    content = path.read_text(errors="ignore")
                    total += len(re.findall(r"\btest\s*\(", content))
                except OSError as err:
                    _log_suppressed("read test file", err)
            return total

        source_counts = {
            "unit": _count_py("**/tests/unit/**/*.py"),
            "integration": _count_py("**/tests/integration/**/*.py"),
            "tour": _count_py("**/tests/tour/**/*.py"),
            "js": _count_js(),
        }

        # Load per-phase aggregates into results when available
        summaries: dict[str, dict[str, object]] = {}
        for phase in ("unit", "js", "integration", "tour"):
            phase_dir = self.session_dir / phase if self.session_dir else None
            agg = None
            try:
                if phase_dir and (phase_dir / "all.summary.json").exists():
                    import json as _json

                    agg = _json.loads((phase_dir / "all.summary.json").read_text())
            except (OSError, ValueError) as exc:
                _log_suppressed("read phase summary", exc)
                agg = None
            summaries[phase] = agg or {}
        retcodes = {k: o.return_code for k, o in outcomes.items()}
        aggregate = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "session": self.session_name,
            "start_time": self.session_started,
            "end_time": time.time(),
            "elapsed_seconds": time.time() - self.session_started,
            "results": summaries,
            "return_codes": retcodes,
            "success": not any_fail,
            "counters_source": source_counts,
            "counters_source_total": sum(int(count_value or 0) for count_value in source_counts.values()),
        }

        # Merge per-phase aggregate counters if present (best-effort)
        def _sum_counter(key: str) -> int:
            total = 0
            for phase_key in ("unit", "js", "integration", "tour"):
                summary = summaries.get(phase_key) or {}
                counters_raw = summary.get("counters")
                counters = counters_raw if isinstance(counters_raw, dict) else {}
                try:
                    total += int(counters.get(key, 0))
                except (TypeError, ValueError) as error:
                    _log_suppressed("sum counter", error)
            return total

        aggregate["counters_total"] = {
            "tests_run": _sum_counter("tests_run"),
            "failures": _sum_counter("failures"),
            "errors": _sum_counter("errors"),
            "skips": _sum_counter("skips"),
        }

        # Write artifacts
        (self.session_dir / "summary.json").write_text(json.dumps(aggregate, indent=2))
        write_manifest(self.session_dir)
        write_latest_json(self.session_dir)
        write_digest(self.session_dir, aggregate)
        write_session_index(self.session_dir, aggregate)
        update_latest_symlink(self.session_dir)
        # JUnit CI artifacts and weight cache update
        try:
            for phase_name in ("unit", "js", "integration", "tour"):
                write_junit_for_phase(self.session_dir, phase_name)
            from .reporter import write_junit_root as _root

            _root(self.session_dir)
            from .reporter import update_weight_cache_from_session as _uw

            _uw(self.session_dir)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("write junit artifacts", exc)

        # Clear 'current'
        try:
            current_path = Path("tmp/test-logs") / "current"
            if current_path.exists() or current_path.is_symlink():
                current_path.unlink()
            current_json_path = current_path.with_suffix(".json")
            if current_json_path.exists():
                current_json_path.unlink()
        except OSError as exc:
            _log_suppressed("clear current pointer", exc)

        if not any_fail:
            print("\n✅ All categories passed")
            print(f"📁 Logs: {self.session_dir}")
            print("🟢 Everything is green")
            return 0

        print("\n❌ Some categories failed")
        for name, outcome in outcomes.items():
            if outcome.return_code is None:
                status = "SKIPPED"
            elif outcome.return_code == 0:
                status = "OK"
            else:
                status = "FAIL"
            print(f"  {name:<11} {status}  → {self.session_dir}")
        print(f"📁 Logs: {self.session_dir}")
        print("🔴 Overall: NOT GREEN")
        for name in ("unit", "js", "integration", "tour"):
            outcome = outcomes.get(name)
            if not outcome:
                continue
            return_code = outcome.return_code
            if return_code is not None and return_code != 0:
                return return_code
        return 1

    # ————— High‑level run —————
    def run(self) -> int:
        print("🧪 Running tests with parallel sharding")
        self._begin()
        # Pre-run orphan cleanup (best-effort): remove stale test DBs/filestores from previous runs
        try:
            root = get_production_db_name()
            cleanup_test_databases(root)
            cleanup_filestores(root)
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("pre-run cleanup", exc)
        assert self.session_dir is not None
        timeouts = _load_timeouts()

        def _timeout(key: str, default: int) -> int:
            raw = timeouts.get(key, default)
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default

        # Discover modules per category
        unit_modules = self._discover_unit_modules()
        js_modules = self._discover_js_modules()
        integration_modules = self._discover_integration_modules()
        tour_modules = self._discover_tour_modules()

        # Prefetch heavy assets (template DB, first filestore snapshots) in background
        self._prefetch_heavy_assets(integration_modules, tour_modules)

        outcomes: dict[str, PhaseOutcome] = {}

        try:
            if self.settings.phases_overlap:
                from concurrent.futures import ThreadPoolExecutor

                # Unit + JS in parallel
                with ThreadPoolExecutor(max_workers=2) as pool:
                    self._emit_event("phase_start", phase="unit")
                    self._emit_event("phase_start", phase="js")
                    unit_future = pool.submit(self._run_unit_sharded, unit_modules, _timeout("unit", 600))
                    js_future = pool.submit(self._run_js_sharded, js_modules, _timeout("js", 1200))
                    outcomes["unit"] = unit_future.result()
                    outcomes["js"] = js_future.result()
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "unit")
                        aggregate_phase(self.session_dir, "js")
                except (OSError, RuntimeError, ValueError) as exc:
                    _log_suppressed("aggregate unit/js", exc)
                # Proceed or stop based on keep_going
                if not self.keep_going and (not outcomes["unit"].ok or not outcomes["js"].ok):
                    outcomes.setdefault("integration", PhaseOutcome("integration", None, None, None))
                    outcomes.setdefault("tour", PhaseOutcome("tour", None, None, None))
                    return self._finish(outcomes)
                # Integration + Tour in parallel
                with ThreadPoolExecutor(max_workers=2) as secondary_pool:
                    self._emit_event("phase_start", phase="integration")
                    self._emit_event("phase_start", phase="tour")
                    integration_future = secondary_pool.submit(
                        self._run_integration_sharded,
                        integration_modules,
                        _timeout("integration", 900),
                    )
                    tour_future = secondary_pool.submit(self._run_tour_sharded, tour_modules, _timeout("tour", 1800))
                    outcomes["integration"] = integration_future.result()
                    outcomes["tour"] = tour_future.result()
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "integration")
                        aggregate_phase(self.session_dir, "tour")
                except (OSError, RuntimeError, ValueError) as exc:
                    _log_suppressed("aggregate integration/tour", exc)
                return self._finish(outcomes)
            else:
                # Sequential path
                self._emit_event("phase_start", phase="unit")
                outcomes["unit"] = self._run_unit_sharded(unit_modules, _timeout("unit", 600))
                if self.keep_going or outcomes["unit"].ok:
                    self._emit_event("phase_start", phase="js")
                    outcomes["js"] = self._run_js_sharded(js_modules, _timeout("js", 1200))
                else:
                    outcomes["js"] = PhaseOutcome("js", None, None, None)
                    print("   Skipping JS tests due to unit failures")
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "unit")
                        aggregate_phase(self.session_dir, "js")
                except (OSError, RuntimeError, ValueError) as exc:
                    _log_suppressed("aggregate unit/js", exc)
                if self.keep_going or (outcomes["js"].ok if outcomes["js"].ok is not None else True):
                    self._emit_event("phase_start", phase="integration")
                    outcomes["integration"] = self._run_integration_sharded(integration_modules, _timeout("integration", 900))
                else:
                    outcomes["integration"] = PhaseOutcome("integration", None, None, None)
                    print("   Skipping integration due to earlier failures")
                if self.keep_going or (outcomes["integration"].ok if outcomes["integration"].ok is not None else True):
                    self._emit_event("phase_start", phase="tour")
                    outcomes["tour"] = self._run_tour_sharded(tour_modules, _timeout("tour", 1800))
                else:
                    outcomes["tour"] = PhaseOutcome("tour", None, None, None)
                    print("   Skipping tour due to earlier failures")
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "integration")
                        aggregate_phase(self.session_dir, "tour")
                except (OSError, RuntimeError, ValueError) as exc:
                    _log_suppressed("aggregate integration/tour", exc)
                return self._finish(outcomes)
        finally:
            # Post-run cleanup (success or cancellation): remove all test DBs/filestores
            try:
                root = get_production_db_name()
                cleanup_test_databases(root)
                cleanup_filestores(root)
            except (OSError, RuntimeError, ValueError) as exc:
                _log_suppressed("post-run cleanup", exc)

        raise RuntimeError("test session finished without a return code")

    def _ensure_template_db(self) -> str:
        if self._template_db:
            return self._template_db
        base = get_production_db_name()
        # Optional reuse across sessions
        if self.settings.reuse_template:
            from .db import template_reuse_candidate

            cand = template_reuse_candidate(base, int(self.settings.template_ttl_sec))
            if cand:
                self._template_db = cand
                return cand
        # Derive from session name to avoid collisions and make cleanup easy
        suffix = (self.session_name or "template").replace("test-", "")
        name = f"{base}_test_template_{suffix}"
        create_template_from_production(name)
        # Record for future reuse if enabled
        if self.settings.reuse_template:
            from .db import record_template

            record_template(name)
        self._template_db = name
        return name

    def _prefetch_heavy_assets(self, integration_modules: list[str], tour_modules: list[str]) -> None:
        # Run template creation and first filestore snapshot in background while unit/js may be running
        import threading

        # Start template DB creation if needed
        def _ensure_template() -> None:
            try:
                self._ensure_template_db()
            except (OSError, RuntimeError, ValueError) as exc:
                _log_suppressed("ensure template db", exc)

        t1 = threading.Thread(target=_ensure_template, daemon=True)
        t1.start()

        # Optionally pre-snapshot first integration/tour filestores when not skipped
        from .filestore import snapshot_filestore
        settings = self.settings

        def _maybe_snapshot_first(phase: str, modules: list[str], skip_flag: bool) -> None:
            try:
                if skip_flag or not modules:
                    return
                shards = self._compute_shards(
                    modules,
                    default_auto=2,
                    env_value=(settings.integration_shards if phase == "integration" else settings.tour_shards),
                    phase=phase,
                )
                if not shards or not shards[0]:
                    return
                first_mods = shards[0]
                base = f"{settings.db_name}_test_{phase}"
                db = base if len(shards) == 1 else f"{base}_{abs(hash('-'.join(first_mods))) % 10_000}"
                snapshot_filestore(db, get_production_db_name())
            except (OSError, RuntimeError, ValueError) as exc:
                _log_suppressed("prefetch filestore", exc)

        if integration_modules and not settings.skip_filestore_integration:
            threading.Thread(target=_maybe_snapshot_first, args=("integration", integration_modules, False), daemon=True).start()
        if tour_modules and not settings.skip_filestore_tour:
            threading.Thread(target=_maybe_snapshot_first, args=("tour", tour_modules, False), daemon=True).start()

    # ————— Discovery helpers —————
    def _discover_unit_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["**/tests/unit/**/*.py"]) or self._all_modules()
        return self._apply_filters(modules, phase="unit")

    def _discover_js_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["static/tests/**/*.test.js"]) or self._all_modules()
        return self._apply_filters(modules, phase="js")

    def _discover_integration_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["**/tests/integration/**/*.py"]) or self._all_modules()
        return self._apply_filters(modules, phase="integration")

    def _discover_tour_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["**/tests/tour/**/*.py"]) or self._all_modules()
        return self._apply_filters(modules, phase="tour")

    @staticmethod
    def _manifest_modules(patterns: list[str]) -> list[str]:
        return discover_modules_with(patterns)

    def _all_modules(self) -> list[str]:
        addons_root = Path("addons")
        modules: list[str] = []
        if not addons_root.exists():
            return modules
        for addon_dir in addons_root.iterdir():
            if addon_dir.is_dir() and (addon_dir / "__manifest__.py").exists():
                name = addon_dir.name
                lower_name = name.lower()
                if any(marker in lower_name for marker in ("backup", "codex", "_bak", "~")):
                    continue
                modules.append(name)
        return self._apply_filters(modules, phase=None)

    def _apply_filters(self, modules: list[str], phase: str | None) -> list[str]:
        if not modules:
            return modules
        filtered_modules = modules
        if self._include:
            filtered_modules = [module_name for module_name in filtered_modules if module_name in self._include]
        if self._exclude:
            filtered_modules = [module_name for module_name in filtered_modules if module_name not in self._exclude]
        if phase:
            phase_include = self._p_include.get(phase) or set()
            phase_exclude = self._p_exclude.get(phase) or set()
            if phase_include:
                filtered_modules = [
                    module_name for module_name in filtered_modules if module_name in phase_include
                ]
            if phase_exclude:
                filtered_modules = [
                    module_name for module_name in filtered_modules if module_name not in phase_exclude
                ]
        # Keep original order but de-dup just in case
        seen: set[str] = set()
        deduped: list[str] = []
        for module_name in filtered_modules:
            if module_name in seen:
                continue
            seen.add(module_name)
            deduped.append(module_name)
        return deduped

    # ————— Sharded runners —————
    def _run_unit_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.unit_within_shards)
        if within and within > 0:
            class_shards = self._compute_within_shards(modules, within, phase="unit")
            if not class_shards or len(class_shards) < within:
                return self._fanout_method("unit", modules, timeout, within)
            return self._fanout_class("unit", class_shards, timeout)
        shards = self._compute_shards(modules, default_auto=4, env_value=self.settings.unit_shards, phase="unit")
        return self._fanout("unit", shards, timeout)

    def _run_js_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.js_shards, phase="js")
        return self._fanout("js", shards, timeout)

    def _run_integration_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.integration_within_shards)
        if within and within > 0:
            class_shards = self._compute_within_shards(modules, within, phase="integration")
            # If class-level sharding yields fewer shards than requested, fall back to method-level slicing
            if not class_shards or len(class_shards) < within:
                return self._fanout_method("integration", modules, timeout, within)
            return self._fanout_class("integration", class_shards, timeout)
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.integration_shards, phase="integration")
        return self._fanout("integration", shards, timeout)

    def _run_tour_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.tour_within_shards)
        if within and within > 0:
            class_shards = self._compute_within_shards(modules, within, phase="tour")
            if not class_shards or len(class_shards) < within:
                return self._fanout_method("tour", modules, timeout, within)
            return self._fanout_class("tour", class_shards, timeout)
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.tour_shards, phase="tour")
        return self._fanout("tour", shards, timeout)

    def _compute_shards(self, modules: list[str], default_auto: int, env_value: int, phase: str | None = None) -> list[list[str]]:
        if not modules:
            return [[]]
        shard_count = env_value
        if shard_count <= 0:
            # very rough auto selection; can be tuned later
            try:
                import os as _os

                cpu = max(1, len(_os.sched_getaffinity(0)))  # type: ignore[attr-defined]
            except (AttributeError, OSError, ValueError) as exc:
                _log_suppressed("detect cpu", exc)
                cpu = os.cpu_count() or 4
            shard_count = max(1, min(cpu, default_auto))
        shard_count = max(1, min(shard_count, len(modules)))
        # Soft cap by DB connections (dynamic)
        try:
            from .db import db_capacity

            max_conn, active = db_capacity()
            per_shard = max(1, int(self.settings.conn_per_shard))
            reserve = int(self.settings.conn_reserve)
            allowed = max(1, (max_conn - active - reserve) // per_shard)
            if shard_count > allowed:
                print(
                    "⚠️  Reducing shards from "
                    f"{shard_count} to {allowed} due to DB connection guardrail "
                    f"(max={max_conn}, active={active}, per_shard={per_shard})"
                )
                shard_count = allowed
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("db capacity guardrail", exc)
        if phase:
            plan = plan_shards_for_phase(modules, phase, shard_count)
            return [
                [module_entry["name"] for module_entry in shard["modules"]] for shard in plan.shards
            ]
        return greedy_shards(modules, shard_count)

    @staticmethod
    def _compute_within_shards(modules: list[str], within: int, *, phase: str) -> list[list[dict]]:
        from .sharding import plan_within_module_shards

        shards = plan_within_module_shards(modules, phase, max(1, within))
        out: list[list[dict]] = []
        for shard in shards:
            out.append([
                {"module": item.module, "class": item.cls, "weight": item.weight} for item in shard
            ])
        return out

    def _cap_by_db_guardrail(self, shard_count: int) -> int:
        try:
            from .db import db_capacity

            max_conn, active = db_capacity()
            per_shard = max(1, int(self.settings.conn_per_shard))
            reserve = int(self.settings.conn_reserve)
            allowed = max(1, (max_conn - active - reserve) // per_shard)
            return max(1, min(shard_count, allowed))
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("db guardrail", exc)
            return max(1, shard_count)

    @staticmethod
    def _aggregate_futures(futures: dict) -> int:
        from concurrent.futures import as_completed

        aggregate_return_code = 0
        for future in as_completed(futures):
            return_code = future.result()
            if return_code != 0:
                aggregate_return_code = aggregate_return_code or return_code
        return aggregate_return_code

    @staticmethod
    def _run_parallel(items: list[_T], max_workers: int, runner: Callable[[_T], int]) -> int:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(runner, item): item for item in items}
            return TestSession._aggregate_futures(futures)

    def _run_fanout(
        self,
        session_dir: Path,
        phase: str,
        shards: list[_T],
        max_workers: int,
        runner: Callable[[_T], int],
    ) -> PhaseOutcome:
        aggregate_return_code = self._run_parallel(shards, max_workers, runner)
        return PhaseOutcome(
            phase,
            0 if aggregate_return_code == 0 else aggregate_return_code,
            session_dir / phase,
            None,
        )

    def _fanout_shards(self, phase: str, shards: list[_T], runner: Callable[[_T], int]) -> PhaseOutcome:
        assert self.session_dir is not None
        max_workers = int(self.settings.max_procs) if self.settings.max_procs else min(8, len(shards))
        return self._run_fanout(self.session_dir, phase, shards, max_workers, runner)

    def _fanout_method(self, phase: str, modules: list[str], timeout: int, slice_count: int) -> PhaseOutcome:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from .executor import OdooExecutor

        assert self.session_dir is not None
        session_dir = self.session_dir
        slice_count = self._cap_by_db_guardrail(max(1, int(slice_count)))
        print(f"▶️  Phase {phase} with {slice_count} method-slice shard(s)")

        def _run(slice_index: int) -> int:
            executor = OdooExecutor(session_dir, phase)
            is_js = phase == "js"
            is_tour = phase == "tour"
            use_prod = phase in {"integration", "tour"}
            base_tag = "js_test" if is_js else ("tour_test" if is_tour else ("integration_test" if use_prod else "unit_test"))
            tag_expr = base_tag
            db_base = f"{self.settings.db_name}_test_{phase}"
            db_name = f"{db_base}_m{slice_index:03d}"
            template_db = self._ensure_template_db() if use_prod else None
            extra_env = {
                "OAI_TEST_SLICER": "1",
                "TEST_SLICE_TOTAL": str(slice_count),
                "TEST_SLICE_INDEX": str(slice_index),
                "TEST_SLICE_PHASE": phase,
                "TEST_SLICE_MODULES": ",".join(modules),
                "PYTHONPATH": "/volumes/tools/testkit:$PYTHONPATH",
            }
            return executor.run(
                test_tags=tag_expr,
                db_name=db_name,
                modules_to_install=modules,
                timeout=timeout,
                is_tour_test=is_tour,
                is_js_test=is_js,
                use_production_clone=use_prod,
                template_db=template_db,
                extra_env=extra_env,
                shard_label=f"ms{slice_index:03d}",
            ).returncode

        max_workers = int(self.settings.max_procs) if self.settings.max_procs else min(8, slice_count)
        aggregate_return_code = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run, slice_index): slice_index for slice_index in range(slice_count)}
            for future in as_completed(futures):
                return_code = future.result()
                if return_code != 0:
                    aggregate_return_code = aggregate_return_code or return_code
        return PhaseOutcome(
            phase,
            0 if aggregate_return_code == 0 else aggregate_return_code,
            self.session_dir / phase,
            None,
        )

    def _fanout(self, phase: str, shards: list[list[str]], timeout: int) -> PhaseOutcome:
        from .executor import OdooExecutor

        assert self.session_dir is not None
        session_dir = self.session_dir
        print(f"▶️  Phase {phase} with {len(shards)} shard(s)")

        def _run(shard_modules: list[str]) -> int:
            if not shard_modules:
                return 0
            executor = OdooExecutor(session_dir, phase)
            # Use per-module prefix to create separate log files when shard is single module
            use_prefix = len(shard_modules) == 1
            is_js = phase == "js"
            is_tour = phase == "tour"
            use_prod = phase in {"integration", "tour"}
            tags = "js_test" if is_js else ("tour_test,-js_test" if is_tour else ("integration_test" if use_prod else "unit_test"))
            db = f"{self.settings.db_name}_test_{phase}"
            template_db = self._ensure_template_db() if use_prod else None
            return executor.run(
                test_tags=tags,
                db_name=db if len(shards) == 1 else f"{db}_{abs(hash('-'.join(shard_modules))) % 10_000}",
                modules_to_install=shard_modules,
                timeout=timeout,
                is_tour_test=is_tour,
                is_js_test=is_js,
                use_production_clone=use_prod,
                template_db=template_db,
                use_module_prefix=use_prefix,
            ).returncode

        return self._fanout_shards(phase, shards, _run)

    def _fanout_class(self, phase: str, shards: list[list[dict]], timeout: int) -> PhaseOutcome:
        from .executor import OdooExecutor

        assert self.session_dir is not None
        session_dir = self.session_dir
        print(f"▶️  Phase {phase} with {len(shards)} class-shard(s)")

        def _run(class_items: list[dict]) -> int:
            if not class_items:
                return 0
            is_js = phase == "js"
            is_tour = phase == "tour"
            use_prod = phase in {"integration", "tour"}
            base_tag = "js_test" if is_js else ("tour_test" if is_tour else ("integration_test" if use_prod else "unit_test"))
            modules = sorted({item["module"] for item in class_items})
            parts = [f"{base_tag}/{item['module']}:{item['class']}" for item in class_items]
            if is_tour:
                parts.append("-js_test")
            tag_expr = ",".join(parts)
            executor = OdooExecutor(session_dir, phase)
            db = f"{self.settings.db_name}_test_{phase}"
            template_db = self._ensure_template_db() if use_prod else None
            return executor.run(
                test_tags=tag_expr,
                db_name=f"{db}_{abs(hash('::'.join(parts))) % 10_000}",
                modules_to_install=modules,
                timeout=timeout,
                is_tour_test=is_tour,
                is_js_test=is_js,
                use_production_clone=use_prod,
                template_db=template_db,
            ).returncode

        return self._fanout_shards(phase, shards, _run)
