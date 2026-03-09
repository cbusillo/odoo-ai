import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from tools.environment_files import discover_repo_root

from .coverage import finalize_coverage, prepare_coverage_directory
from .db import (
    cleanup_test_databases,
    create_template_from_production,
    get_production_db_name,
    wait_for_database_ready,
)
from .docker_api import (
    cleanup_orphan_testkit_containers,
    cleanup_testkit_db_volume,
    ensure_named_volume_permissions,
    ensure_services_up,
    get_database_service,
    get_script_runner_service,
)
from .executor import OdooExecutor, ShardExecutionRequest
from .filestore import cleanup_filestores
from .phases import PhaseOutcome
from .plan import ClassShardItem, PhaseExecutionPlan, PhaseName, RunExecutionPlan, TemplateStrategy
from .reporter import (
    aggregate_phase,
    begin_session_dir,
    prune_old_sessions,
    update_latest_symlink,
    write_digest,
    write_junit_for_phase,
    write_latest_json,
    write_manifest,
    write_run_plan,
    write_session_index,
)
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings
from .sharding import discover_modules_with, greedy_shards, plan_shards_for_phase

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class PreflightError(RuntimeError):
    def __init__(self, message: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.detail = detail


def _log_suppressed(action: str, exc: Exception) -> None:
    _logger.debug("testkit session: %s failed (%s)", action, exc)


def _load_timeouts() -> dict:
    try:
        import tomllib  # Python 3.11+

        repo_root = discover_repo_root(Path.cwd())
        pyproject_file_path = repo_root / "pyproject.toml"
        with pyproject_file_path.open("rb") as file_handle:
            data = tomllib.load(file_handle)
        return data.get("tool", {}).get("odoo-test", {}).get("timeouts", {}) or {}
    except (OSError, ValueError):
        return {}


def _stable_hash_suffix(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:8]


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
        self._events = None
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
        self._template_failed = False
        self._template_lock = threading.Lock()
        self._phase_templates: dict[str, str] = {}
        self._phase_template_failed: set[str] = set()
        self._phase_template_locks: dict[str, threading.Lock] = {
            "unit": threading.Lock(),
            "js": threading.Lock(),
        }
        self._preflight_state = {"services": False, "template": False}
        self._preflight_started: float | None = None
        self._preflight_steps: list[dict[str, object]] = []
        self._preflight_report: dict[str, object] = {}
        self._shard_plans: dict[str, dict[str, object]] = {}
        self._host_resource_semaphores: dict[str, threading.BoundedSemaphore] = {}
        browser_slots = max(1, int(self.settings.browser_slots))
        production_clone_slots = max(1, int(self.settings.production_clone_slots))
        self._host_resource_limits = {
            "browser": browser_slots,
            "production_clone": production_clone_slots,
        }
        self._host_resource_semaphores = {
            "browser": threading.BoundedSemaphore(browser_slots),
            "production_clone": threading.BoundedSemaphore(production_clone_slots),
        }

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

    def plan_phase(self, phase: PhaseName, shard_override: int | None = None) -> dict[str, object]:
        timeout = self._phase_timeout(phase)
        phase_plan = self.build_phase_plan(phase, timeout=timeout, shard_override=shard_override)
        return phase_plan.to_payload()

    def build_phase_plan(
        self,
        phase: PhaseName,
        *,
        timeout: int,
        shard_override: int | None = None,
        modules: list[str] | None = None,
    ) -> PhaseExecutionPlan:
        phase_modules = list(modules) if modules is not None else self.discover_modules(phase)
        if not phase_modules:
            return PhaseExecutionPlan(
                phase=phase,
                modules=(),
                timeout=timeout,
                strategy="empty",
                requested_shards=shard_override,
                effective_shards=0,
                max_workers=0,
                template_strategy=self._template_strategy_for_phase(phase),
                uses_browser=self._phase_uses_browser(phase),
                uses_production_clone=self._phase_uses_production_clone(phase),
            )

        default_auto = 4 if phase == "unit" else 2
        requested_shards, within_shards = self._phase_shard_inputs_from_settings(
            phase,
            shard_override,
            self.settings,
        )
        template_strategy = self._template_strategy_for_phase(phase)
        uses_browser = self._phase_uses_browser(phase)
        uses_production_clone = self._phase_uses_production_clone(phase)

        if within_shards and phase in {"unit", "integration", "tour"}:
            class_shards = self._compute_within_shards(phase_modules, within_shards, phase=phase)
            if class_shards and len(class_shards) >= within_shards:
                effective_shards = len(class_shards)
                return PhaseExecutionPlan(
                    phase=phase,
                    modules=tuple(phase_modules),
                    timeout=timeout,
                    strategy="class_sharding",
                    requested_shards=within_shards,
                    effective_shards=effective_shards,
                    max_workers=self._resolve_phase_max_workers(phase, effective_shards),
                    template_strategy=template_strategy,
                    uses_browser=uses_browser,
                    uses_production_clone=uses_production_clone,
                    class_shards=tuple(
                        tuple(
                            ClassShardItem(
                                module=class_item["module"],
                                class_name=class_item["class"],
                                weight=int(class_item["weight"]),
                            )
                            for class_item in shard
                        )
                        for shard in class_shards
                    ),
                )

            slice_count = self._cap_by_db_guardrail(max(1, int(within_shards)))
            return PhaseExecutionPlan(
                phase=phase,
                modules=tuple(phase_modules),
                timeout=timeout,
                strategy="method_slicing",
                requested_shards=within_shards,
                effective_shards=slice_count,
                max_workers=self._resolve_phase_max_workers(phase, slice_count),
                template_strategy=template_strategy,
                uses_browser=uses_browser,
                uses_production_clone=uses_production_clone,
                slice_count=slice_count,
            )

        computed_shards = self._compute_shards(
            phase_modules,
            default_auto=default_auto,
            env_value=int(requested_shards),
            phase=phase,
        )
        plan = self._shard_plans.get(phase) or {}
        effective_shards = len(computed_shards)
        requested_value = plan.get("requested")
        auto_selected = plan.get("auto_selected")
        module_cap = plan.get("module_cap")
        db_guarded = plan.get("db_guarded")
        total_weight = plan.get("total_weight")
        return PhaseExecutionPlan(
            phase=phase,
            modules=tuple(phase_modules),
            timeout=timeout,
            strategy=str(plan.get("strategy") or "module_sharding"),
            requested_shards=requested_value if isinstance(requested_value, int) else requested_shards,
            effective_shards=effective_shards,
            max_workers=self._resolve_phase_max_workers(phase, effective_shards),
            template_strategy=template_strategy,
            uses_browser=uses_browser,
            uses_production_clone=uses_production_clone,
            auto_selected=auto_selected if isinstance(auto_selected, int) else None,
            module_cap=module_cap if isinstance(module_cap, int) else None,
            db_guarded=db_guarded if isinstance(db_guarded, int) else None,
            total_weight=total_weight if isinstance(total_weight, int) else None,
            module_shards=tuple(tuple(shard_modules) for shard_modules in computed_shards),
        )

    def build_run_plan(self) -> RunExecutionPlan:
        phase_names: tuple[PhaseName, ...] = ("unit", "js", "integration", "tour")
        phase_plans = tuple(self.build_phase_plan(phase, timeout=self._phase_timeout(phase)) for phase in phase_names)
        if self.settings.phases_overlap:
            phase_groups: tuple[tuple[PhaseName, ...], ...] = (("unit", "js"), ("integration", "tour"))
        else:
            phase_groups = (("unit",), ("js",), ("integration",), ("tour",))
        return RunExecutionPlan(
            phases=phase_plans,
            phase_groups=phase_groups,
            overlap_enabled=bool(self.settings.phases_overlap),
            browser_slots=max(1, int(self.settings.browser_slots)),
            production_clone_slots=max(1, int(self.settings.production_clone_slots)),
        )

    @staticmethod
    def _phase_timeout(phase: PhaseName) -> int:
        defaults = {
            "unit": 600,
            "js": 1200,
            "integration": 900,
            "tour": 1800,
        }
        configured_timeouts = _load_timeouts()
        raw_timeout = configured_timeouts.get(phase, defaults[phase])
        try:
            return int(raw_timeout)
        except (TypeError, ValueError):
            return defaults[phase]

    @staticmethod
    def _phase_shard_inputs_from_settings(
        phase: PhaseName,
        shard_override: int | None,
        settings: TestSettings,
    ) -> tuple[int, int]:
        if phase == "unit":
            return shard_override if shard_override is not None else int(settings.unit_shards), int(settings.unit_within_shards)
        if phase == "integration":
            return (
                shard_override if shard_override is not None else int(settings.integration_shards),
                int(settings.integration_within_shards),
            )
        if phase == "tour":
            return shard_override if shard_override is not None else int(settings.tour_shards), int(settings.tour_within_shards)
        return shard_override if shard_override is not None else int(settings.js_shards), 0

    @staticmethod
    def _template_strategy_for_phase(phase: PhaseName) -> TemplateStrategy:
        if phase in {"unit", "js"}:
            return "phase"
        if phase in {"integration", "tour"}:
            return "production"
        return "none"

    @staticmethod
    def _phase_uses_browser(phase: PhaseName) -> bool:
        return phase in {"js", "tour"}

    @staticmethod
    def _phase_uses_production_clone(phase: PhaseName) -> bool:
        return phase in {"integration", "tour"}

    def run_phase(self, phase: PhaseName, modules: list[str], timeout: int) -> PhaseOutcome:
        try:
            self._preflight(need_template=False)
        except RuntimeError as error:
            self._emit_event("preflight_failed", phase=phase, error=str(error))
            return PhaseOutcome(phase, 1, None, None)
        phase_plan = self.build_phase_plan(phase, modules=modules, timeout=timeout)
        self._prepare_phase_resources(phase_plan)
        return self._execute_phase_plan(phase_plan)

    def _begin(self) -> None:
        self.session_dir, self.session_name, self.session_started = begin_session_dir()
        os.environ["TEST_LOG_SESSION"] = self.session_name or ""
        prepare_coverage_directory(self.settings, self.session_dir)
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
        if self._events is None:
            return
        try:
            self._events.emit(event, **payload)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            _log_suppressed(f"emit {event}", exc)

    def _require_session_dir(self) -> Path:
        if self.session_dir is None:
            raise RuntimeError("Session directory unavailable. Call _begin() before running phase operations.")
        return self.session_dir

    def _require_session_state(self) -> tuple[Path, str]:
        session_dir = self._require_session_dir()
        if not self.session_name:
            raise RuntimeError("Session name unavailable. Call _begin() before finishing the run.")
        return session_dir, self.session_name

    def _record_preflight_step(
        self,
        name: str,
        action: Callable[[], object | None],
    ) -> None:
        start = time.time()
        self._emit_event("preflight_step_start", name=name)
        error_message = None
        detail: object | None = None
        try:
            detail = action()
            success = True
        except Exception as error:
            success = False
            error_message = str(error)
            error_detail = getattr(error, "detail", None)
            if error_detail not in (None, "", {}, []):
                detail = error_detail
        elapsed = time.time() - start
        step = {
            "name": name,
            "ok": success,
            "elapsed_seconds": elapsed,
        }
        if detail not in (None, "", {}, []):
            step["detail"] = detail
        if error_message:
            step["error"] = error_message
        self._preflight_steps.append(step)
        self._emit_event("preflight_step", **step)
        if not success:
            raise RuntimeError(f"Preflight step '{name}' failed: {error_message}")

    def _preflight(self, *, need_template: bool) -> None:
        if self._preflight_started is None:
            self._preflight_started = time.time()
            self._emit_event("preflight_start", session=self.session_name)

        try:
            if not self._preflight_state.get("services"):

                def _validate_structure() -> dict[str, object]:
                    from .validate import check_test_structure

                    report = check_test_structure(Path("addons"))
                    if not report.get("ok"):
                        raise PreflightError("Test structure validation failed", detail=report)
                    return report

                def _cleanup_orphans() -> dict[str, object]:
                    return cleanup_orphan_testkit_containers()

                def _ensure_services() -> dict[str, object]:
                    services = [get_database_service(), get_script_runner_service()]
                    ensure_services_up(services)
                    return {"services": services}

                def _wait_database() -> dict[str, object]:
                    if not wait_for_database_ready():
                        raise RuntimeError("Database did not become ready")
                    return {"ready": True}

                self._record_preflight_step("validate_test_structure", _validate_structure)
                self._record_preflight_step("cleanup_orphan_containers", _cleanup_orphans)
                self._record_preflight_step("ensure_services", _ensure_services)
                self._record_preflight_step("wait_for_database", _wait_database)
                self._record_preflight_step("ensure_named_volume_permissions", ensure_named_volume_permissions)
                self._preflight_state["services"] = True

            if need_template and not self._preflight_state.get("template"):

                def _ensure_template() -> dict[str, object]:
                    template_name = self._ensure_template_db()
                    return {"template_db": template_name}

                self._record_preflight_step("ensure_template_db", _ensure_template)
                self._preflight_state["template"] = True
        finally:
            end_time = time.time()
            started = self._preflight_started or end_time
            self._preflight_report = {
                "start_time": started,
                "end_time": end_time,
                "elapsed_seconds": end_time - started,
                "steps": list(self._preflight_steps),
            }
            self._emit_event("preflight_end", elapsed_seconds=end_time - started)

    def _finish(self, outcomes: dict[str, PhaseOutcome]) -> int:
        session_dir, _session_name = self._require_session_state()
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
            for path in Path("addons").glob("**/static/tests/**/*.test.js"):
                if path.is_file():
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

        # Ensure per-phase aggregates exist even for single-phase runs
        summaries: dict[str, dict[str, object]] = {}
        for phase in ("unit", "js", "integration", "tour"):
            phase_dir = session_dir / phase
            if phase_dir and not (phase_dir / "all.summary.json").exists():
                try:
                    aggregate_phase(session_dir, phase)
                except (OSError, RuntimeError, ValueError) as exc:
                    _log_suppressed("aggregate phase", exc)
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
        stack_name = (os.environ.get("ODOO_STACK_NAME") or "").strip() or None
        env_file = (os.environ.get("TESTKIT_ENV_FILE") or "").strip() or None
        aggregate = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "session": self.session_name,
            "start_time": self.session_started,
            "end_time": time.time(),
            "elapsed_seconds": time.time() - self.session_started,
            "environment": {
                "project_name": self.settings.project_name,
                "stack_name": stack_name,
                "env_file": env_file,
                "db_name": self.settings.db_name,
                "shard_timeout": self.settings.shard_timeout,
            },
            "results": summaries,
            "return_codes": retcodes,
            "success": not any_fail,
            "counters_source": source_counts,
            "counters_source_total": sum(int(count_value or 0) for count_value in source_counts.values()),
        }

        try:
            coverage_payload = finalize_coverage(self.settings, session_dir)
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("finalize coverage", exc)
            coverage_payload = None
        if coverage_payload:
            aggregate["coverage"] = coverage_payload

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

        if self._preflight_report:
            aggregate["preflight"] = self._preflight_report
        if self._shard_plans:
            aggregate["sharding"] = self._shard_plans
        aggregate["artifacts"] = {
            "events": str(session_dir / "events.ndjson"),
        }

        # Write artifacts
        (session_dir / "summary.json").write_text(json.dumps(aggregate, indent=2))
        write_latest_json(session_dir)
        try:
            from .reporter import write_llm_report

            write_llm_report(session_dir, aggregate)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("write llm report", exc)
        write_digest(session_dir, aggregate)
        write_session_index(session_dir, aggregate)
        update_latest_symlink(session_dir)
        # JUnit CI artifacts and weight cache update
        try:
            for phase_name in ("unit", "js", "integration", "tour"):
                write_junit_for_phase(session_dir, phase_name)
            from .reporter import write_junit_root as _root

            _root(session_dir)
            from .reporter import update_weight_cache_from_session as _uw

            _uw(session_dir)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("write junit artifacts", exc)

        try:
            write_manifest(session_dir)
        except OSError as exc:
            _log_suppressed("write manifest", exc)

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

        try:
            cleanup_testkit_db_volume()
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("cleanup testkit db volume", exc)

        llm_path = session_dir / "llm.json"

        if not any_fail:
            print("\n✅ All categories passed")
            print(f"📁 Logs: {session_dir}")
            if llm_path.exists():
                print(f"🤖 LLM summary: {llm_path}")
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
            print(f"  {name:<11} {status}  → {session_dir}")
        print(f"📁 Logs: {session_dir}")
        if llm_path.exists():
            print(f"🤖 LLM summary: {llm_path}")
        print("🔴 Overall: NOT GREEN")
        for name in ("unit", "js", "integration", "tour"):
            phase_outcome = outcomes.get(name)
            if not phase_outcome:
                continue
            return_code = phase_outcome.return_code
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
        session_dir = self._require_session_dir()
        run_plan = self.build_run_plan()
        write_run_plan(session_dir, run_plan.to_payload())
        self._emit_event(
            "plan_committed",
            overlap_enabled=run_plan.overlap_enabled,
            phase_groups=[list(phase_group) for phase_group in run_plan.phase_groups],
        )

        try:
            self._preflight(need_template=False)
        except RuntimeError as error:
            self._emit_event("preflight_failed", error=str(error))
            preflight_outcomes = {name: PhaseOutcome(name, None, None, None) for name in ("unit", "js", "integration", "tour")}
            preflight_outcomes["unit"] = PhaseOutcome("unit", 1, None, None)
            return self._finish(preflight_outcomes)

        outcomes: dict[str, PhaseOutcome] = {}

        try:
            for phase_group in run_plan.phase_groups:
                group_plans = [run_plan.phase(phase_name) for phase_name in phase_group]
                self._prepare_phase_group_resources(group_plans)
                if len(group_plans) == 1:
                    phase_plan = group_plans[0]
                    outcomes[phase_plan.phase] = self._execute_planned_phase(phase_plan)
                else:
                    outcomes.update(self._execute_phase_group(group_plans))
                if not self.keep_going and any(outcomes[phase_name].ok is False for phase_name in phase_group):
                    for remaining_phase in ("unit", "js", "integration", "tour"):
                        outcomes.setdefault(remaining_phase, PhaseOutcome(remaining_phase, None, None, None))
                    return self._finish(outcomes)
            return self._finish(outcomes)
        finally:
            # Post-run cleanup (success or cancellation): remove all test DBs/filestores
            try:
                root = get_production_db_name()
                cleanup_test_databases(root)
                cleanup_filestores(root)
            except (OSError, RuntimeError, ValueError) as exc:
                _log_suppressed("post-run cleanup", exc)

    def _prepare_phase_group_resources(self, phase_plans: list[PhaseExecutionPlan]) -> None:
        for phase_plan in phase_plans:
            self._prepare_phase_resources(phase_plan)

    def _prepare_phase_resources(self, phase_plan: PhaseExecutionPlan) -> None:
        if phase_plan.is_empty:
            return
        if phase_plan.template_strategy == "production":
            template_name = self._ensure_template_db()
            self._emit_event("phase_resources_ready", phase=phase_plan.phase, template_db=template_name)
            return
        if phase_plan.template_strategy == "phase":
            template_name = self._ensure_phase_template_db(
                phase_plan.phase,
                list(phase_plan.modules),
                phase_plan.timeout,
            )
            self._emit_event("phase_resources_ready", phase=phase_plan.phase, template_db=template_name)

    def _execute_phase_group(self, phase_plans: list[PhaseExecutionPlan]) -> dict[str, PhaseOutcome]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        outcomes: dict[str, PhaseOutcome] = {}
        with ThreadPoolExecutor(max_workers=len(phase_plans)) as pool:
            futures = {pool.submit(self._execute_planned_phase, phase_plan): phase_plan.phase for phase_plan in phase_plans}
            for future in as_completed(futures):
                outcomes[futures[future]] = future.result()
        return outcomes

    def _execute_planned_phase(self, phase_plan: PhaseExecutionPlan) -> PhaseOutcome:
        self._emit_event("phase_start", phase=phase_plan.phase)
        outcome = self._execute_phase_plan(phase_plan)
        try:
            if self.session_dir:
                aggregate_phase(self.session_dir, phase_plan.phase)
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed(f"aggregate {phase_plan.phase}", exc)
        return outcome

    def _execute_phase_plan(self, phase_plan: PhaseExecutionPlan) -> PhaseOutcome:
        if phase_plan.is_empty:
            return PhaseOutcome(phase_plan.phase, 0, self._require_session_dir() / phase_plan.phase, None)
        if phase_plan.strategy == "class_sharding":
            return self._execute_shard_requests(
                phase_plan.phase,
                self._build_class_shard_requests(phase_plan),
                label="class-shard",
                max_workers=phase_plan.max_workers,
            )
        if phase_plan.strategy == "method_slicing":
            return self._execute_shard_requests(
                phase_plan.phase,
                self._build_method_slice_requests(phase_plan),
                label="method-slice shard",
                max_workers=phase_plan.max_workers,
            )
        if phase_plan.module_shards:
            return self._execute_shard_requests(
                phase_plan.phase,
                self._build_module_shard_requests(phase_plan),
                label="shard",
                max_workers=phase_plan.max_workers,
            )
        raise ValueError(f"Unsupported phase plan strategy: {phase_plan.strategy}")

    def _ensure_template_db(self) -> str | None:
        if self._template_failed:
            return None
        if self._template_db:
            return self._template_db
        with self._template_lock:
            if self._template_failed:
                return None
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
            try:
                create_template_from_production(name, timeout_sec=600)
            except Exception as error:
                _logger.warning("template db creation failed (%s)", error)
                self._template_failed = True
                return None
            # Record for future reuse if enabled
            if self.settings.reuse_template:
                from .db import record_template

                record_template(name)
            self._template_db = name
            return name

    def _ensure_phase_template_db(self, phase: str, modules: list[str], timeout: int) -> str | None:
        if phase not in {"unit", "js"}:
            return None
        if not modules:
            return None
        if phase in self._phase_template_failed:
            return None
        cached = self._phase_templates.get(phase)
        if cached:
            return cached
        lock = self._phase_template_locks.get(phase)
        if lock is None:
            return None
        with lock:
            cached = self._phase_templates.get(phase)
            if cached:
                return cached
            if phase in self._phase_template_failed:
                return None
            session_dir = self._require_session_dir()
            base = get_production_db_name()
            module_key = ",".join(sorted(modules))
            hash_prefix = hashlib.sha1(module_key.encode()).hexdigest()[:8]
            suffix = (self.session_name or "template").replace("test-", "")
            template_name = f"{base}_test_template_{phase}_{hash_prefix}_{suffix}"
            log_dir = session_dir / phase
            log_path = log_dir / f"template-{hash_prefix}.log"
            try:
                from .db import build_module_template

                print(f"🧱 Building {phase} template with {len(modules)} module(s)")
                build_module_template(template_name, modules, timeout_sec=timeout, log_path=log_path)
            except Exception as error:
                _logger.warning("phase template build failed for %s (%s)", phase, error)
                self._phase_template_failed.add(phase)
                return None
            self._phase_templates[phase] = template_name
            return template_name

    # ————— Discovery helpers —————
    def _discover_unit_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["**/tests/unit/**/*.py"]) or self._all_modules()
        return self._apply_filters(modules, phase="unit")

    def _discover_js_modules(self) -> list[str]:
        modules = self._manifest_modules(patterns=["**/static/tests/**/*.test.js"]) or self._all_modules()
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
                filtered_modules = [module_name for module_name in filtered_modules if module_name in phase_include]
            if phase_exclude:
                filtered_modules = [module_name for module_name in filtered_modules if module_name not in phase_exclude]
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
        phase_plan = self.build_phase_plan("unit", modules=modules, timeout=timeout)
        self._prepare_phase_resources(phase_plan)
        return self._execute_phase_plan(phase_plan)

    def _run_js_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        phase_plan = self.build_phase_plan("js", modules=modules, timeout=timeout)
        self._prepare_phase_resources(phase_plan)
        return self._execute_phase_plan(phase_plan)

    def _run_integration_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        phase_plan = self.build_phase_plan("integration", modules=modules, timeout=timeout)
        self._prepare_phase_resources(phase_plan)
        return self._execute_phase_plan(phase_plan)

    def _run_tour_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        phase_plan = self.build_phase_plan("tour", modules=modules, timeout=timeout)
        self._prepare_phase_resources(phase_plan)
        return self._execute_phase_plan(phase_plan)

    def _compute_shards(self, modules: list[str], default_auto: int, env_value: int, phase: str | None = None) -> list[list[str]]:
        if not modules:
            return [[]]
        shard_count = env_value
        requested_shards = env_value if env_value > 0 else None
        auto_selected: int | None = None
        if shard_count <= 0:
            # very rough auto selection; can be tuned later
            try:
                import os as _os

                cpu = max(1, len(_os.sched_getaffinity(0)))  # type: ignore[attr-defined]
            except (AttributeError, OSError, ValueError) as exc:
                _log_suppressed("detect cpu", exc)
                cpu = os.cpu_count() or 4
            auto_selected = max(1, min(cpu, default_auto))
            shard_count = auto_selected
        shard_count = max(1, min(shard_count, len(modules)))
        module_capped = shard_count
        db_guarded = shard_count
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
            db_guarded = shard_count
        except (OSError, RuntimeError, ValueError) as exc:
            _log_suppressed("db capacity guardrail", exc)
        if phase:
            plan = plan_shards_for_phase(modules, phase, shard_count)
            self._shard_plans[phase] = {
                "requested": requested_shards,
                "auto_selected": auto_selected,
                "module_cap": module_capped,
                "db_guarded": db_guarded,
                "effective": plan.shards_count,
                "modules": len(modules),
                "total_weight": plan.total_weight,
                "strategy": plan.strategy,
                "shards": plan.shards,
            }
            return [[module_entry["name"] for module_entry in shard["modules"]] for shard in plan.shards]
        return greedy_shards(modules, shard_count)

    @staticmethod
    def _compute_within_shards(modules: list[str], within: int, *, phase: str) -> list[list[dict]]:
        from .sharding import plan_within_module_shards

        shards = plan_within_module_shards(modules, phase, max(1, within))
        out: list[list[dict]] = []
        for shard in shards:
            out.append([{"module": item.module, "class": item.cls, "weight": item.weight} for item in shard])
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

    def _fanout_shards(
        self,
        phase: str,
        shards: list[_T],
        runner: Callable[[_T], int],
        *,
        max_workers: int | None = None,
    ) -> PhaseOutcome:
        session_dir = self._require_session_dir()
        effective_workers = max_workers if max_workers is not None else self._resolve_phase_max_workers(phase, len(shards))
        return self._run_fanout(session_dir, phase, shards, effective_workers, runner)

    @staticmethod
    def _phase_base_tag(phase: str) -> str:
        if phase == "js":
            return "js_test"
        if phase == "tour":
            return "tour_test"
        if phase == "integration":
            return "integration_test"
        return "unit_test"

    def _phase_db_base(self, phase: str) -> str:
        return f"{self.settings.db_name}_test_{phase}"

    @staticmethod
    def _phase_uses_prod_template(phase: str) -> bool:
        return phase in {"integration", "tour"}

    def _template_db_for_phase(self, phase: str, modules: list[str], timeout: int) -> str | None:
        if self._phase_uses_prod_template(phase):
            return self._ensure_template_db()
        return self._ensure_phase_template_db(phase, modules, timeout)

    def _make_shard_request(
        self,
        phase: str,
        *,
        modules: list[str],
        timeout: int,
        test_tags: str,
        db_name: str,
        template_db: str | None,
        use_module_prefix: bool = False,
        extra_env: dict[str, str] | None = None,
        shard_label: str | None = None,
    ) -> ShardExecutionRequest:
        return ShardExecutionRequest(
            test_tags=test_tags,
            db_name=db_name,
            modules_to_install=tuple(modules),
            timeout=timeout,
            is_tour_test=phase == "tour",
            is_js_test=phase == "js",
            use_production_clone=self._phase_uses_prod_template(phase),
            template_db=template_db,
            use_module_prefix=use_module_prefix,
            extra_env=extra_env,
            shard_label=shard_label,
        )

    def _build_method_slice_requests(self, phase_plan: PhaseExecutionPlan) -> list[ShardExecutionRequest]:
        modules = list(phase_plan.modules)
        slice_count = self._cap_by_db_guardrail(max(1, int(phase_plan.slice_count)))
        template_db = self._template_db_for_phase(phase_plan.phase, modules, phase_plan.timeout)
        db_base = self._phase_db_base(phase_plan.phase)
        requests: list[ShardExecutionRequest] = []
        for slice_index in range(slice_count):
            shard_env = {
                "OAI_TEST_SLICER": "1",
                "TEST_SLICE_TOTAL": str(slice_count),
                "TEST_SLICE_INDEX": str(slice_index),
                "TEST_SLICE_PHASE": phase_plan.phase,
                "TEST_SLICE_MODULES": ",".join(modules),
            }
            requests.append(
                self._make_shard_request(
                    phase_plan.phase,
                    modules=modules,
                    timeout=phase_plan.timeout,
                    test_tags=self._phase_base_tag(phase_plan.phase),
                    db_name=f"{db_base}_m{slice_index:03d}",
                    template_db=template_db,
                    extra_env=shard_env,
                    shard_label=f"ms{slice_index:03d}",
                )
            )
        return requests

    def _build_module_shard_requests(self, phase_plan: PhaseExecutionPlan) -> list[ShardExecutionRequest]:
        shards = [list(shard_modules) for shard_modules in phase_plan.module_shards]
        phase_modules = sorted({module_name for shard in shards for module_name in shard})
        template_db = self._template_db_for_phase(phase_plan.phase, phase_modules, phase_plan.timeout)
        test_tags = self._phase_base_tag(phase_plan.phase)
        if phase_plan.phase == "tour":
            test_tags = "tour_test,-js_test"
        db_base = self._phase_db_base(phase_plan.phase)
        requests: list[ShardExecutionRequest] = []
        for shard_modules in shards:
            if not shard_modules:
                continue
            db_name = db_base if len(shards) == 1 else f"{db_base}_{_stable_hash_suffix('-'.join(shard_modules))}"
            requests.append(
                self._make_shard_request(
                    phase_plan.phase,
                    modules=shard_modules,
                    timeout=phase_plan.timeout,
                    test_tags=test_tags,
                    db_name=db_name,
                    template_db=template_db,
                    use_module_prefix=len(shard_modules) == 1,
                )
            )
        return requests

    def _build_class_shard_requests(self, phase_plan: PhaseExecutionPlan) -> list[ShardExecutionRequest]:
        template_db = self._template_db_for_phase(phase_plan.phase, list(phase_plan.modules), phase_plan.timeout)
        base_tag = self._phase_base_tag(phase_plan.phase)
        db_base = self._phase_db_base(phase_plan.phase)
        requests: list[ShardExecutionRequest] = []
        for shard in phase_plan.class_shards:
            modules = sorted({class_item.module for class_item in shard})
            parts = [f"{base_tag}/{class_item.module}:{class_item.class_name}" for class_item in shard]
            if phase_plan.phase == "tour":
                parts.append("-js_test")
            requests.append(
                self._make_shard_request(
                    phase_plan.phase,
                    modules=modules,
                    timeout=phase_plan.timeout,
                    test_tags=",".join(parts),
                    db_name=f"{db_base}_{_stable_hash_suffix('::'.join(parts))}",
                    template_db=template_db,
                )
            )
        return requests

    def _execute_shard_requests(
        self,
        phase: str,
        requests: list[ShardExecutionRequest],
        *,
        label: str,
        max_workers: int | None = None,
    ) -> PhaseOutcome:
        session_dir = self._require_session_dir()
        effective_workers = self._effective_workers_for_requests(phase, requests, max_workers=max_workers)
        print(f"▶️  Phase {phase} with {len(requests)} {label}(s)")

        def _run(request: ShardExecutionRequest) -> int:
            with self._acquire_host_resources_for_request(request):
                return OdooExecutor(session_dir, phase).run_request(request).returncode

        return self._fanout_shards(phase, requests, _run, max_workers=effective_workers)

    @staticmethod
    def _request_resource_names(request: ShardExecutionRequest) -> tuple[str, ...]:
        resource_names: list[str] = []
        if request.use_production_clone:
            resource_names.append("production_clone")
        if request.is_js_test or request.is_tour_test:
            resource_names.append("browser")
        return tuple(resource_names)

    def _host_resource_limit_for_requests(self, requests: list[ShardExecutionRequest]) -> int | None:
        if not requests:
            return None
        shared_resources = set(self._request_resource_names(requests[0]))
        if not shared_resources:
            return None
        for request in requests[1:]:
            shared_resources &= set(self._request_resource_names(request))
        if not shared_resources:
            return None
        return min(self._host_resource_limits[resource_name] for resource_name in shared_resources)

    def _effective_workers_for_requests(
        self,
        phase: str,
        requests: list[ShardExecutionRequest],
        *,
        max_workers: int | None,
    ) -> int:
        configured_workers = max_workers if max_workers is not None else self._resolve_phase_max_workers(phase, len(requests))
        resource_limit = self._host_resource_limit_for_requests(requests)
        if resource_limit is None:
            return configured_workers
        return max(1, min(configured_workers, resource_limit))

    @contextmanager
    def _acquire_host_resources_for_request(self, request: ShardExecutionRequest) -> Iterator[None]:
        semaphores = [self._host_resource_semaphores[resource_name] for resource_name in self._request_resource_names(request)]
        acquired: list[threading.BoundedSemaphore] = []
        try:
            for semaphore in semaphores:
                semaphore.acquire()
                acquired.append(semaphore)
            yield
        finally:
            for semaphore in reversed(acquired):
                semaphore.release()

    def _resolve_phase_max_workers(self, phase: str, shard_count: int) -> int:
        if shard_count <= 0:
            return 0
        if phase == "tour" and int(self.settings.tour_max_procs) > 0:
            return max(1, min(int(self.settings.tour_max_procs), shard_count))
        if self.settings.max_procs:
            return max(1, min(int(self.settings.max_procs), shard_count))
        cpu_count = self._detect_cpu_count()
        if phase == "unit":
            return max(1, min(shard_count, cpu_count))
        if phase == "integration":
            return max(1, min(shard_count, max(1, cpu_count // 2)))
        if phase == "js":
            return max(1, min(shard_count, max(1, min(2, cpu_count // 4 or 1))))
        return 1

    @staticmethod
    def _detect_cpu_count() -> int:
        try:
            return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
        except (AttributeError, OSError, ValueError):
            return max(1, os.cpu_count() or 4)
