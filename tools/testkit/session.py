from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .db import cleanup_test_databases, create_template_from_production, get_production_db_name
from .filestore import cleanup_filestores
from .phases import IntegrationPhase, JsPhase, PhaseOutcome, TourPhase, UnitPhase
from .reporter import (
    aggregate_phase,
    begin_session_dir,
    prune_old_sessions,
    update_latest_symlink,
    write_digest,
    write_latest_json,
    write_manifest,
    write_session_index,
)
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings
from .sharding import discover_modules_with, greedy_shards, plan_shards_for_phase


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

    def _begin(self) -> None:
        self.session_dir, self.session_name, self.session_started = begin_session_dir()
        os.environ["TEST_LOG_SESSION"] = self.session_name or ""
        # Events stream
        from .events import EventStream

        self._events = EventStream((self.session_dir / "events.ndjson"), echo=self.settings.events_stdout)
        try:
            self._events.emit("session_started", session=self.session_name)
        except Exception:
            pass
        # prune older sessions
        try:
            prune_old_sessions(Path("tmp/test-logs"), max(1, int(self.settings.test_log_keep)))
        except Exception:
            pass
        # in-progress pointer
        try:
            cur = Path("tmp/test-logs") / "current"
            try:
                if cur.exists() or cur.is_symlink():
                    cur.unlink()
            except OSError:
                pass
            rel = os.path.relpath(self.session_dir, cur.parent)
            try:
                cur.symlink_to(rel)
            except OSError:
                (cur.with_suffix(".json")).write_text(
                    json.dumps({"schema_version": SUMMARY_SCHEMA_VERSION, "current": str(self.session_dir)}, indent=2)
                )
        except OSError:
            pass

    def _finish(self, outcomes: dict[str, PhaseOutcome]) -> int:
        assert self.session_dir and self.session_name
        any_fail = any(o.return_code not in (None, 0) for o in outcomes.values())

        # Source counts (definition counts)
        def _count_py(glob_pattern: str) -> int:
            try:
                total = 0
                for p in Path("addons").glob(glob_pattern):
                    if p.is_file() and p.suffix == ".py":
                        try:
                            txt = p.read_text(errors="ignore")
                            total += len(re.findall(r"^\s*def\s+test_", txt, flags=re.MULTILINE))
                        except OSError:
                            pass
                return total
            except Exception:
                return 0

        def _count_js() -> int:
            try:
                total = 0
                for p in Path("addons").rglob("*.test.js"):
                    try:
                        txt = p.read_text(errors="ignore")
                        total += len(re.findall(r"\btest\s*\(", txt))
                    except OSError:
                        pass
                return total
            except Exception:
                return 0

        source_counts = {
            "unit": _count_py("**/tests/unit/**/*.py"),
            "integration": _count_py("**/tests/integration/**/*.py"),
            "tour": _count_py("**/tests/tour/**/*.py"),
            "js": _count_js(),
        }

        # Load per-phase aggregates into results when available
        summaries: dict[str, dict] = {}
        for ph in ("unit", "js", "integration", "tour"):
            ph_dir = self.session_dir / ph if self.session_dir else None
            agg = None
            try:
                if ph_dir and (ph_dir / "all.summary.json").exists():
                    import json as _json

                    agg = _json.loads((ph_dir / "all.summary.json").read_text())
            except Exception:
                agg = None
            summaries[ph] = agg or {}
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
            "counters_source_total": sum(int(v or 0) for v in source_counts.values()),
        }

        # Merge per-phase aggregate counters if present (best-effort)
        def _sum_counter(key: str) -> int:
            total = 0
            for k in ("unit", "js", "integration", "tour"):
                s = aggregate["results"].get(k) or {}
                c = (s.get("counters") or {}) if isinstance(s, dict) else {}
                try:
                    total += int(c.get(key, 0))
                except (TypeError, ValueError):
                    pass
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
            for ph in ("unit", "js", "integration", "tour"):
                write_junit_for_phase(self.session_dir, ph)
            from .reporter import write_junit_root as _root

            _root(self.session_dir)
            from .reporter import update_weight_cache_from_session as _uw

            _uw(self.session_dir)
        except Exception:
            pass
        # JUnit CI artifacts and weight cache update
        try:
            for ph in ("unit", "js", "integration", "tour"):
                write_junit_for_phase(self.session_dir, ph)
            from .reporter import write_junit_root as _root

            _root(self.session_dir)
            from .reporter import update_weight_cache_from_session as _uw

            _uw(self.session_dir)
        except Exception:
            pass

        # Clear 'current'
        try:
            cur = Path("tmp/test-logs") / "current"
            if cur.exists() or cur.is_symlink():
                cur.unlink()
            cj = cur.with_suffix(".json")
            if cj.exists():
                cj.unlink()
        except OSError:
            pass

        if not any_fail:
            print("\n✅ All categories passed")
            print(f"📁 Logs: {self.session_dir}")
            print("🟢 Everything is green")
            return 0

        print("\n❌ Some categories failed")
        for name, o in outcomes.items():
            if o.return_code is None:
                status = "SKIPPED"
            elif o.return_code == 0:
                status = "OK"
            else:
                status = "FAIL"
            print(f"  {name:<11} {status}  → {self.session_dir}")
        print(f"📁 Logs: {self.session_dir}")
        print("🔴 Overall: NOT GREEN")
        for name in ("unit", "js", "integration", "tour"):
            o = outcomes.get(name)
            if o and o.return_code and o.return_code != 0:
                return int(o.return_code)
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
        except Exception:
            pass
        assert self.session_dir is not None
        timeouts = _load_timeouts()

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
                    try:
                        self._events.emit("phase_start", phase="unit")
                    except Exception:
                        pass
                    try:
                        self._events.emit("phase_start", phase="js")
                    except Exception:
                        pass
                    fu = pool.submit(self._run_unit_sharded, unit_modules, timeouts.get("unit", 600))
                    fj = pool.submit(self._run_js_sharded, js_modules, timeouts.get("js", 1200))
                    outcomes["unit"] = fu.result()
                    outcomes["js"] = fj.result()
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "unit")
                        aggregate_phase(self.session_dir, "js")
                except Exception:
                    pass
                # Proceed or stop based on keep_going
                if not self.keep_going and (not outcomes["unit"].ok or not outcomes["js"].ok):
                    outcomes.setdefault("integration", PhaseOutcome("integration", None, None, None))
                    outcomes.setdefault("tour", PhaseOutcome("tour", None, None, None))
                    return self._finish(outcomes)
                # Integration + Tour in parallel
                with ThreadPoolExecutor(max_workers=2) as pool2:
                    try:
                        self._events.emit("phase_start", phase="integration")
                    except Exception:
                        pass
                    try:
                        self._events.emit("phase_start", phase="tour")
                    except Exception:
                        pass
                    fi = pool2.submit(self._run_integration_sharded, integration_modules, timeouts.get("integration", 900))
                    ft = pool2.submit(self._run_tour_sharded, tour_modules, timeouts.get("tour", 1800))
                    outcomes["integration"] = fi.result()
                    outcomes["tour"] = ft.result()
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "integration")
                        aggregate_phase(self.session_dir, "tour")
                except Exception:
                    pass
                return self._finish(outcomes)
            else:
                # Sequential path
                try:
                    self._events.emit("phase_start", phase="unit")
                except Exception:
                    pass
                outcomes["unit"] = self._run_unit_sharded(unit_modules, timeouts.get("unit", 600))
                if self.keep_going or outcomes["unit"].ok:
                    try:
                        self._events.emit("phase_start", phase="js")
                    except Exception:
                        pass
                    outcomes["js"] = self._run_js_sharded(js_modules, timeouts.get("js", 1200))
                else:
                    outcomes["js"] = PhaseOutcome("js", None, None, None)
                    print("   Skipping JS tests due to unit failures")
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "unit")
                        aggregate_phase(self.session_dir, "js")
                except Exception:
                    pass
                if self.keep_going or (outcomes["js"].ok if outcomes["js"].ok is not None else True):
                    try:
                        self._events.emit("phase_start", phase="integration")
                    except Exception:
                        pass
                    outcomes["integration"] = self._run_integration_sharded(integration_modules, timeouts.get("integration", 900))
                else:
                    outcomes["integration"] = PhaseOutcome("integration", None, None, None)
                    print("   Skipping integration due to earlier failures")
                if self.keep_going or (outcomes["integration"].ok if outcomes["integration"].ok is not None else True):
                    try:
                        self._events.emit("phase_start", phase="tour")
                    except Exception:
                        pass
                    outcomes["tour"] = self._run_tour_sharded(tour_modules, timeouts.get("tour", 1800))
                else:
                    outcomes["tour"] = PhaseOutcome("tour", None, None, None)
                    print("   Skipping tour due to earlier failures")
                try:
                    if self.session_dir:
                        aggregate_phase(self.session_dir, "integration")
                        aggregate_phase(self.session_dir, "tour")
                except Exception:
                    pass
                return self._finish(outcomes)
        finally:
            # Post-run cleanup (success or cancellation): remove all test DBs/filestores
            try:
                root = get_production_db_name()
                cleanup_test_databases(root)
                cleanup_filestores(root)
            except Exception:
                pass

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
            except Exception:
                pass

        t1 = threading.Thread(target=_ensure_template, daemon=True)
        t1.start()

        # Optionally pre-snapshot first integration/tour filestores when not skipped
        from .filestore import snapshot_filestore
        from .settings import TestSettings

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
            except Exception:
                pass

        if integration_modules and not settings.skip_filestore_integration:
            threading.Thread(target=_maybe_snapshot_first, args=("integration", integration_modules, False), daemon=True).start()
        if tour_modules and not settings.skip_filestore_tour:
            threading.Thread(target=_maybe_snapshot_first, args=("tour", tour_modules, False), daemon=True).start()

    # ————— Discovery helpers —————
    def _discover_unit_modules(self) -> list[str]:
        mods = self._manifest_modules(patterns=["**/tests/unit/**/*.py"]) or self._all_modules()
        return self._apply_filters(mods, phase="unit")

    def _discover_js_modules(self) -> list[str]:
        mods = self._manifest_modules(patterns=["static/tests/**/*.test.js"]) or self._all_modules()
        return self._apply_filters(mods, phase="js")

    def _discover_integration_modules(self) -> list[str]:
        mods = self._manifest_modules(patterns=["**/tests/integration/**/*.py"]) or self._all_modules()
        return self._apply_filters(mods, phase="integration")

    def _discover_tour_modules(self) -> list[str]:
        mods = self._manifest_modules(patterns=["**/tests/tour/**/*.py"]) or self._all_modules()
        return self._apply_filters(mods, phase="tour")

    def _manifest_modules(self, patterns: list[str]) -> list[str]:
        return discover_modules_with(patterns)

    def _all_modules(self) -> list[str]:
        addons = Path("addons")
        mods: list[str] = []
        if not addons.exists():
            return mods
        for p in addons.iterdir():
            if p.is_dir() and (p / "__manifest__.py").exists():
                name = p.name
                low = name.lower()
                if any(t in low for t in ("backup", "codex", "_bak", "~")):
                    continue
                mods.append(name)
        return self._apply_filters(mods, phase=None)

    def _apply_filters(self, modules: list[str], phase: str | None) -> list[str]:
        if not modules:
            return modules
        items = modules
        if self._include:
            items = [m for m in items if m in self._include]
        if self._exclude:
            items = [m for m in items if m not in self._exclude]
        if phase:
            p_inc = self._p_include.get(phase) or set()
            p_exc = self._p_exclude.get(phase) or set()
            if p_inc:
                items = [m for m in items if m in p_inc]
            if p_exc:
                items = [m for m in items if m not in p_exc]
        # Keep original order but de-dup just in case
        seen: set[str] = set()
        out: list[str] = []
        for m in items:
            if m in seen:
                continue
            seen.add(m)
            out.append(m)
        return out

    # ————— Sharded runners —————
    def _run_unit_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.unit_within_shards)
        if within and within > 0:
            shards = self._compute_within_shards(modules, within, phase="unit")
            return self._fanout_class("unit", shards, timeout)
        shards = self._compute_shards(modules, default_auto=4, env_value=self.settings.unit_shards, phase="unit")
        return self._fanout("unit", shards, timeout)

    def _run_js_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.js_shards, phase="js")
        return self._fanout("js", shards, timeout)

    def _run_integration_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.integration_within_shards)
        if within and within > 0:
            shards = self._compute_within_shards(modules, within, phase="integration")
            return self._fanout_class("integration", shards, timeout)
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.integration_shards, phase="integration")
        return self._fanout("integration", shards, timeout)

    def _run_tour_sharded(self, modules: list[str], timeout: int) -> PhaseOutcome:
        within = int(self.settings.tour_within_shards)
        if within and within > 0:
            shards = self._compute_within_shards(modules, within, phase="tour")
            return self._fanout_class("tour", shards, timeout)
        shards = self._compute_shards(modules, default_auto=2, env_value=self.settings.tour_shards, phase="tour")
        return self._fanout("tour", shards, timeout)

    def _compute_shards(self, modules: list[str], default_auto: int, env_value: int, phase: str | None = None) -> list[list[str]]:
        if not modules:
            return [[]]
        n = env_value
        if n <= 0:
            # very rough auto selection; can be tuned later
            try:
                import os as _os

                cpu = max(1, len(_os.sched_getaffinity(0)))  # type: ignore[attr-defined]
            except Exception:
                cpu = os.cpu_count() or 4
            n = max(1, min(cpu, default_auto))
        n = max(1, min(n, len(modules)))
        # Soft cap by DB connections (dynamic)
        try:
            from .db import db_capacity

            max_conn, active = db_capacity()
            per_shard = max(1, int(self.settings.conn_per_shard))
            reserve = int(self.settings.conn_reserve)
            allowed = max(1, (max_conn - active - reserve) // per_shard)
            if n > allowed:
                print(
                    f"⚠️  Reducing shards from {n} to {allowed} due to DB connection guardrail (max={max_conn}, active={active}, per_shard={per_shard})"
                )
                n = allowed
        except Exception:
            pass
        if phase:
            plan = plan_shards_for_phase(modules, phase, n)
            return [[m["name"] for m in shard["modules"]] for shard in plan.shards]
        return greedy_shards(modules, n)

    def _compute_within_shards(self, modules: list[str], within: int, *, phase: str) -> list[list[dict]]:
        from .sharding import plan_within_module_shards

        shards = plan_within_module_shards(modules, phase, max(1, within))
        out: list[list[dict]] = []
        for s in shards:
            out.append([{"module": it.module, "class": it.cls, "weight": it.weight} for it in s])
        return out

    def _fanout(self, phase: str, shards: list[list[str]], timeout: int) -> PhaseOutcome:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from .executor import OdooExecutor

        assert self.session_dir is not None
        print(f"▶️  Phase {phase} with {len(shards)} shard(s)")

        def _run(mods: list[str]) -> int:
            if not mods:
                return 0
            ex = OdooExecutor(self.session_dir, phase)
            # Use per-module prefix to create separate log files when shard is single module
            use_prefix = len(mods) == 1
            is_js = phase == "js"
            is_tour = phase == "tour"
            use_prod = phase in {"integration", "tour"}
            tags = "js_test" if is_js else ("tour_test,-js_test" if is_tour else ("integration_test" if use_prod else "unit_test"))
            db = f"{self.settings.db_name}_test_{phase}"
            template_db = self._ensure_template_db() if use_prod else None
            return ex.run(
                test_tags=tags,
                db_name=db if len(shards) == 1 else f"{db}_{abs(hash('-'.join(mods))) % 10_000}",
                modules_to_install=mods,
                timeout=timeout,
                is_tour_test=is_tour,
                is_js_test=is_js,
                use_production_clone=use_prod,
                template_db=template_db,
                use_module_prefix=use_prefix,
            ).returncode

        max_workers = self.settings.max_procs or min(8, len(shards))
        rc_agg = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run, mods): mods for mods in shards}
            for fut in as_completed(futures):
                rc = fut.result()
                if rc != 0:
                    rc_agg = rc_agg or rc
        return PhaseOutcome(phase, 0 if rc_agg == 0 else rc_agg, self.session_dir / phase, None)

    def _fanout_class(self, phase: str, shards: list[list[dict]], timeout: int) -> PhaseOutcome:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from .executor import OdooExecutor

        assert self.session_dir is not None
        print(f"▶️  Phase {phase} with {len(shards)} class-shard(s)")

        def _run(items: list[dict]) -> int:
            if not items:
                return 0
            is_js = phase == "js"
            is_tour = phase == "tour"
            use_prod = phase in {"integration", "tour"}
            base_tag = "js_test" if is_js else ("tour_test" if is_tour else ("integration_test" if use_prod else "unit_test"))
            modules = sorted({i["module"] for i in items})
            parts = [f"{base_tag}/{i['module']}:{i['class']}" for i in items]
            if is_tour:
                parts.append("-js_test")
            tag_expr = ",".join(parts)
            ex = OdooExecutor(self.session_dir, phase)
            db = f"{self.settings.db_name}_test_{phase}"
            template_db = self._ensure_template_db() if use_prod else None
            return ex.run(
                test_tags=tag_expr,
                db_name=f"{db}_{abs(hash('::'.join(parts))) % 10_000}",
                modules_to_install=modules,
                timeout=timeout,
                is_tour_test=is_tour,
                is_js_test=is_js,
                use_production_clone=use_prod,
                template_db=template_db,
                use_module_prefix=False,
            ).returncode

        max_workers = self.settings.max_procs or min(8, len(shards))
        rc_agg = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run, items): items for items in shards}
            for fut in as_completed(futures):
                rc = fut.result()
                if rc != 0:
                    rc_agg = rc_agg or rc
        return PhaseOutcome(phase, 0 if rc_agg == 0 else rc_agg, self.session_dir / phase, None)
