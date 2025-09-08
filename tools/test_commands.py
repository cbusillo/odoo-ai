#!/usr/bin/env python3

import json
import os
import re
import secrets
import select
import string
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import shutil
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Summary schema version for all JSON outputs produced by test runner
SUMMARY_SCHEMA_VERSION = "1.0"


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env", extra="ignore")

    # Core project/env
    project_name: str = Field("odoo", alias="ODOO_PROJECT_NAME")
    db_user: str | None = Field(None, alias="ODOO_DB_USER")
    filestore_path: str | None = Field(None, alias="ODOO_FILESTORE_PATH")
    db_name: str = Field("odoo", alias="ODOO_DB_NAME")

    # Test runner toggles and parameters
    test_unit_split: bool = Field(True, alias="TEST_UNIT_SPLIT")
    test_keep_going: bool = Field(True, alias="TEST_KEEP_GOING")
    test_log_keep: int = Field(12, alias="TEST_LOG_KEEP")
    test_scoped_cleanup: bool = Field(True, alias="TEST_SCOPED_CLEANUP")

    tour_warmup: int = Field(0, alias="TOUR_WARMUP")
    js_workers: int = Field(2, alias="JS_WORKERS")
    tour_workers: int = Field(0, alias="TOUR_WORKERS")

    test_tags_override: str | None = Field(None, alias="TEST_TAGS")
    test_log_session: str | None = Field(None, alias="TEST_LOG_SESSION")


_SETTINGS: TestSettings | None = None


def get_settings() -> "TestSettings":
    global _SETTINGS
    if _SETTINGS is None:
        # noinspection PyArgumentList
        _SETTINGS = TestSettings()
    return _SETTINGS


def normalize_line_for_pattern_detection(line: str) -> str:
    # Remove timestamps like "2025-08-26 02:10:28,708"
    line = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", "[TIMESTAMP]", line)
    # Remove IP addresses like "127.0.0.1"
    line = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]", line)
    # Remove process IDs and other numbers that might vary
    line = re.sub(r"\b\d+\b", "[NUM]", line)
    # Remove version strings like "18.0-5"
    line = re.sub(r"\d+\.\d+(-\d+)?", "[VERSION]", line)
    # Normalize whitespace
    line = " ".join(line.split())

    return line.strip()


def detect_repetitive_pattern(
    recent_lines: list[str], pattern_occurrences: dict[str, int], min_occurrences: int = 5
) -> tuple[bool, str]:
    if len(recent_lines) < min_occurrences:
        return False, ""

    # Update pattern occurrences count for all recent lines
    for line in recent_lines:
        normalized = normalize_line_for_pattern_detection(line)
        if normalized and len(normalized) > 20:  # Ignore very short lines
            pattern_occurrences[normalized] = pattern_occurrences.get(normalized, 0) + 1

    # Find the most common pattern
    if pattern_occurrences:
        most_common_pattern = max(pattern_occurrences.items(), key=lambda x: x[1])
        pattern, count = most_common_pattern

        if count >= min_occurrences:
            # Check if this pattern dominates recent output (>70% of recent lines)
            recent_normalized = [normalize_line_for_pattern_detection(line) for line in recent_lines]
            matching_lines = [norm for norm in recent_normalized if norm == pattern]
            pattern_ratio = len(matching_lines) / len(recent_normalized) if recent_normalized else 0

            if pattern_ratio > 0.7:  # More than 70% of recent lines are the same pattern
                # Extract a readable part of the original pattern
                original_sample = ""
                for line in recent_lines:
                    if normalize_line_for_pattern_detection(line) == pattern:
                        original_sample = line[:100] + "..." if len(line) > 100 else line
                        break

                return True, f"Repetitive pattern detected ({count} times, {pattern_ratio:.1%} of recent output): {original_sample}"

    return False, ""


def kill_browsers_and_zombies() -> None:
    script_runner_service = get_script_runner_service()
    ensure_services_up([script_runner_service])
    # graceful
    for name in ("chrome", "chromium"):
        _compose_exec(script_runner_service, ["pkill", name])
    # force + drivers
    for name in ("chrome", "chromium", "geckodriver", "chromedriver"):
        _compose_exec(script_runner_service, ["pkill", "-9", name])
    # defunct zombies
    _compose_exec(
        script_runner_service,
        ["sh", "-c", "ps aux | grep defunct | awk '{print $2}' | xargs -r kill -9"],
    )


def safe_terminate_process(process: subprocess.Popen) -> None:

    try:
        # First attempt: gentle termination
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        print("WARNING: Process failed to terminate cleanly")

        # Kill any test processes in container
        patterns = [
            "odoo-bin.*test-enable",
            "python.*odoo-bin",
            "timeout.*odoo-bin",
            "chromium",
            "chrome",
        ]

        script_runner_service = get_script_runner_service()
        for pattern in patterns:
            try:
                _compose_exec(script_runner_service, ["pkill", "-f", pattern])
            except OSError:
                pass  # Ignore cleanup failures

    except Exception as e:
        print(f"Error during process termination: {e}")


## Removed: get_container_prefix() was unused after simplifying process handling


def get_database_service() -> str:
    return "database"


def get_production_db_name() -> str:
    return get_settings().db_name


def get_db_user() -> str:
    settings = get_settings()
    return settings.db_user or "odoo"


def get_filestore_root() -> str:
    settings = get_settings()
    return settings.filestore_path or "/volumes/data"


def get_script_runner_service() -> str:
    result = subprocess.run(["docker", "compose", "ps", "--services"], capture_output=True, text=True)
    services = result.stdout.strip().split("\n") if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"


def _compose_exec(service: str, args: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "exec", "-T", service] + args
    return subprocess.run(cmd, capture_output=capture_output, text=True)


## Removed: _compose_run() not used; we use compose exec or native subprocess for streaming


def ensure_services_up(services: list[str]) -> None:
    for s in services:
        subprocess.run(["docker", "compose", "up", "-d", s], capture_output=True)


def load_timeouts() -> dict:
    try:
        import tomli  # type: ignore

        with open("pyproject.toml", "rb") as f:
            data = tomli.load(f)
        return data.get("tool", {}).get("odoo-test", {}).get("timeouts", {}) or {}
    except (OSError, ValueError):
        return {}


def get_our_modules() -> list[str]:
    module_names: list[str] = []
    addons_path = Path("addons")
    if addons_path.exists():
        for module_dir in addons_path.iterdir():
            if not module_dir.is_dir():
                continue
            if (module_dir / "__manifest__.py").exists():
                name = module_dir.name
                # Skip backup/temp/experimental folders
                lowered = name.lower()
                if any(term in lowered for term in ("backup", "codex", "_bak", "~")):
                    continue
                module_names.append(name)
    return module_names


def run_unit_tests(target_modules: list[str] | None = None, *, session_dir: Path | None = None) -> int:
    user_scoped = target_modules is not None and len(target_modules) > 0
    if user_scoped:
        # Keep only valid modules present in our addons directory
        available = set(get_our_modules())
        selected_modules = [m for m in (target_modules or []) if m in available]
        if not selected_modules:
            print("❌ No matching modules found under ./addons for requested unit test run")
            return 1
    else:
        selected_modules = get_our_modules()

    timeout_cfg = load_timeouts().get("unit", 300)

    # Split-by-module mode to avoid aborting on first failing module
    split = get_settings().test_unit_split
    if not split or (user_scoped and len(selected_modules) == 1):
        test_db_name = f"{get_production_db_name()}_test_unit"
        use_prefix = bool(user_scoped)
        return run_docker_test_command(
            "unit_test",
            test_db_name,
            selected_modules,
            timeout=timeout_cfg,
            use_module_prefix=use_prefix,
            category="unit",
            session_dir=session_dir,
        )

    print("🔀 Unit test matrix: per-module runs to collect all failures")
    overall_rc = 0
    results: list[tuple[str, int, Path]] = []
    for module in selected_modules:
        db = f"{get_production_db_name()}_ut_{module}"
        print("-" * 60)
        print(f"▶️  {module}")
        rc = run_docker_test_command("unit_test", db, [module], timeout=timeout_cfg, category="unit", session_dir=session_dir)
        # Find the most recent log dir to report back (best-effort)
        try:
            latest_dir = max((d for d in (Path("tmp/test-logs")).iterdir() if d.is_dir()), key=lambda p: p.name)
        except (ValueError, OSError):
            latest_dir = Path("tmp/test-logs")
        results.append((module, rc, latest_dir))
        overall_rc |= rc != 0

    print("=" * 60)
    print("Unit matrix results:")
    for module, rc, logdir in results:
        print(f"  {module:28} {'OK' if rc == 0 else 'FAIL'}  → {logdir}")
    # When running within a session (run_all_tests), write an aggregate per-phase
    # summary so counters reflect all split runs rather than only the last one.
    if session_dir is not None:
        try:
            _write_phase_aggregate_summary(session_dir, "unit")
        except OSError:
            # Non-fatal: logs still exist per-module
            pass

    return 0 if overall_rc == 0 else 1


def run_integration_tests(*, session_dir: Path | None = None) -> int:
    selected_modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_integration"
    timeout_cfg = load_timeouts().get("integration", 600)
    return run_docker_test_command(
        "integration_test",
        test_db_name,
        selected_modules,
        timeout=timeout_cfg,
        use_production_clone=True,
        use_module_prefix=False,
        category="integration",
        session_dir=session_dir,
    )


def run_tour_tests(*, session_dir: Path | None = None) -> int:
    print("🧪 Starting tour tests...")
    selected_modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_tour"
    print(f"   Database: {test_db_name}")
    print(f"   Modules: {', '.join(selected_modules)}")
    timeout_cfg = load_timeouts().get("tour", 1800)
    # Exclude JS unit tests explicitly from tour runs to avoid double-running
    # browser_js suites here. JS tests have their own phase and settings.
    tour_tags = "tour_test,-js_test"
    return run_docker_test_command(
        tour_tags,
        test_db_name,
        selected_modules,
        timeout=timeout_cfg,
        use_production_clone=True,
        is_tour_test=True,
        use_module_prefix=False,
        category="tour",
        session_dir=session_dir,
    )


def run_js_tests(target_modules: list[str] | None = None, *, session_dir: Path | None = None) -> int:
    if target_modules:
        available = set(get_our_modules())
        selected_modules = [m for m in target_modules if m in available]
        if not selected_modules:
            print("❌ No matching modules found under ./addons for requested JS test run")
            return 1
    else:
        # Default: restrict to addons that actually contain JS tests to reduce install surface
        all_modules = get_our_modules()
        selected_modules = []
        for m in all_modules:
            js_dir = Path(f"addons/{m}/static/tests")
            if js_dir.exists() and any(js_dir.rglob("*.test.js")):
                selected_modules.append(m)
        # Fallback: if none detected, use all custom modules (preserves legacy behavior)
        if not selected_modules:
            selected_modules = all_modules

    test_db_name = f"{get_production_db_name()}_test_js"
    timeout_cfg = load_timeouts().get("js", 1200)
    return run_docker_test_command(
        "js_test",
        test_db_name,
        selected_modules,
        timeout=timeout_cfg,
        is_js_test=True,
        use_module_prefix=False,
        category="js",
        session_dir=session_dir,
    )


def _get_latest_log_summary() -> tuple[Path | None, dict | None]:
    log_root = Path("tmp/test-logs")
    if not log_root.exists():
        return None, None

    forced = get_settings().test_log_session
    latest: Path | None = None
    if forced:
        cand = log_root / forced
        latest = cand if cand.exists() else None
    if latest is None:
        sessions = [d for d in log_root.iterdir() if d.is_dir() and d.name.startswith("test-")]
        if not sessions:
            return None, None
        latest = max(sessions, key=lambda p: p.name)

    # Prefer aggregate summary.json
    root_summary = latest / "summary.json"
    if root_summary.exists():
        try:
            with open(root_summary) as f:
                return latest, json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    # Fallback to latest per-phase summary (search recursively)
    candidates = sorted(latest.rglob("*.summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        try:
            with open(candidates[0]) as f:
                return latest, json.load(f)
        except (OSError, json.JSONDecodeError):
            return latest, None
    return latest, None


def run_all_tests() -> int:
    print("🧪 Running ALL tests (unit → integration → tour)")
    print("=" * 60)

    keep_going = os.environ.get("TEST_KEEP_GOING", "1") != "0"
    # Create a single session directory to aggregate logs/summaries
    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"test-{session_ts}"
    session_dir = Path("tmp/test-logs") / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TEST_LOG_SESSION"] = session_name
    session_started = time.time()

    # Prune older sessions (keep last N)
    try:
        _prune_old_log_sessions()
    except OSError:
        pass
    # Track per-phase logs and summaries for accurate session aggregate
    logs: dict[str, Path | None] = {"unit": None, "js": None, "integration": None, "tour": None}
    summaries: dict[str, dict | None] = {"unit": None, "js": None, "integration": None, "tour": None}

    # 1) Unit tests on clean DB
    print("\n▶️  Phase 1: Unit tests")
    rc_unit = run_unit_tests(session_dir=session_dir)
    logs["unit"], summaries["unit"] = _get_latest_log_summary()

    # 2) JS unit tests (browser) on clean DB with dev assets
    print("\n▶️  Phase 2: JS tests")
    if keep_going or rc_unit == 0:
        rc_js = run_js_tests(session_dir=session_dir)
        logs["js"], summaries["js"] = _get_latest_log_summary()
    else:
        print("   Skipping JS tests due to unit failures (set TEST_KEEP_GOING=1 to force)")
        rc_js = None

    # 3) Integration tests on cloned DB
    print("\n▶️  Phase 3: Integration tests")
    if keep_going or (rc_js == 0 if rc_js is not None else True):
        rc_integration = run_integration_tests(session_dir=session_dir)
        logs["integration"], summaries["integration"] = _get_latest_log_summary()
    else:
        print("   Skipping integration due to earlier failures (set TEST_KEEP_GOING=1 to force)")
        rc_integration = None

    # 4) Tour tests (browser) on cloned DB
    print("\n▶️  Phase 4: Tour tests")
    if keep_going or (rc_integration == 0 if rc_integration is not None else True):
        rc_tour = run_tour_tests(session_dir=session_dir)
        logs["tour"], summaries["tour"] = _get_latest_log_summary()
    else:
        print("   Skipping tours due to earlier failures (set TEST_KEEP_GOING=1 to force)")
        rc_tour = None

    any_fail = any(code is not None and code != 0 for code in (rc_unit, rc_js, rc_integration, rc_tour))
    # Build aggregate summary for the whole session
    aggregate = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "session": session_name,
        "start_time": session_started,
        "end_time": time.time(),
        "elapsed_seconds": time.time() - session_started,
        "results": {
            "unit": summaries.get("unit"),
            "js": summaries.get("js"),
            "integration": summaries.get("integration"),
            "tour": summaries.get("tour"),
        },
        "return_codes": {
            "unit": rc_unit,
            "js": rc_js,
            "integration": rc_integration,
            "tour": rc_tour,
        },
        "success": not any_fail,
    }

    # Aggregate counters across phases when available
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

    # Write aggregate summary at session root
    agg_path = session_dir / "summary.json"
    try:
        with open(agg_path, "w") as f:
            json.dump(aggregate, f, indent=2, default=str)
        _write_manifest(session_dir)
        _write_latest_json(session_dir)
        _write_digest(session_dir, aggregate)
    except (OSError, json.JSONDecodeError):
        pass

    # Write a simple index.md for quick navigation and update latest symlink
    try:
        _write_session_index(session_dir, aggregate)
        _update_latest_symlink(session_dir)
    except OSError:
        pass

    if not any_fail:
        print("\n✅ All categories passed")
        print(f"📁 Logs: {session_dir}")
        # Final footer line for quick scanning in terminals/IDE consoles
        print("🟢 Everything is green")
        return 0
    else:
        print("\n❌ Some categories failed")
        print("Results:")

        def _fmt(cat: str, code: int | None) -> str:
            log = session_dir
            summ = summaries.get(cat) or {}
            if code is None:
                status = "SKIPPED"
            else:
                if code == 0:
                    status = "OK"
                else:
                    if summ.get("timeout"):
                        status = "TIMEOUT"
                    elif summ.get("repetitive_pattern"):
                        status = "STALLED"
                    elif summ.get("cleanup_hang"):
                        status = "CLEANUP-HANG"
                    else:
                        status = "FAIL"
            extra = f"  → {log}" if log else ""
            return f"  {cat:<11} {status}{extra}"

        print(_fmt("unit", rc_unit))
        print(_fmt("js", rc_js))
        print(_fmt("integration", rc_integration))
        print(_fmt("tour", rc_tour))
        print(f"📁 Logs: {session_dir}")
        # Final footer line for quick scanning in terminals/IDE consoles
        print("🔴 Overall: NOT GREEN")
        # Return first non-zero code for conventional CI semantics
        for code in (rc_unit, rc_js, rc_integration, rc_tour):
            if code and code != 0:
                return code
        return 1


def _write_session_index(session_dir: Path, aggregate: dict) -> None:
    ok = aggregate.get("success", False)
    overall = "PASSED" if ok else "FAILED"
    lines: list[str] = [
        f"# Test Session {aggregate.get('session', session_dir.name)}",
        "",
        f"Overall: {overall}",
        "",
        "## Phases",
    ]
    for cat in ("unit", "js", "integration", "tour"):
        cat_dir = session_dir / cat
        if not cat_dir.exists():
            continue
        entries = []
        for session_file in sorted(cat_dir.glob("*.summary.json")):
            base = session_file.stem.replace(".summary", "")
            log = session_file.with_suffix("").with_suffix(".log")
            entries.append(f"- {cat}: {base} → {session_file.name} / {log.name}")
        if entries:
            lines.append(f"### {cat.title()}")
            lines.extend(entries)
            lines.append("")
    (session_dir / "index.md").write_text("\n".join(lines))


def _update_latest_symlink(session_dir: Path) -> None:
    latest = Path("tmp/test-logs") / "latest"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
    except OSError:
        pass
    rel = os.path.relpath(session_dir, latest.parent)
    try:
        latest.symlink_to(rel)
    except OSError:
        # On systems without symlink support, write a pointer file
        latest.with_suffix(".json").write_text(
            json.dumps({"schema_version": SUMMARY_SCHEMA_VERSION, "latest": str(session_dir)}, indent=2)
        )


def _write_latest_json(session_dir: Path) -> None:
    latest_json = Path("tmp/test-logs") / "latest.json"
    data = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "latest": str(session_dir),
    }
    latest_json.write_text(json.dumps(data, indent=2))


def _write_manifest(session_dir: Path) -> None:
    manifest = {"schema_version": SUMMARY_SCHEMA_VERSION, "files": []}
    for p in session_dir.rglob("*"):
        if p.is_file():
            try:
                stat = p.stat()
                manifest["files"].append(
                    {
                        "path": str(p.relative_to(session_dir)),
                        "bytes": stat.st_size,
                        "mtime": int(stat.st_mtime),
                    }
                )
            except OSError:
                pass
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _write_digest(session_dir: Path, aggregate: dict) -> None:
    cats = {}
    for cat in ("unit", "js", "integration", "tour"):
        s = aggregate.get("results", {}).get(cat) or {}
        if not isinstance(s, dict):
            s = {}
        cats[cat] = {
            "success": bool(s.get("success")) if "success" in s else None,
            "returncode": s.get("returncode"),
            "counters": s.get("counters"),
            "summary_file": s.get("summary_file"),
            "log_file": s.get("log_file"),
            "failures_file": s.get("failures_file"),
            "reason": s.get("reason"),
        }
    digest = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "session": aggregate.get("session"),
        "success": aggregate.get("success"),
        "elapsed_seconds": aggregate.get("elapsed_seconds"),
        "counters_total": aggregate.get("counters_total"),
        "categories": cats,
    }
    (session_dir / "digest.json").write_text(json.dumps(digest, indent=2))


def _write_phase_aggregate_summary(session_dir: Path, category: str) -> Path | None:
    phase_dir = session_dir / category
    if not phase_dir.exists():
        return None

    parts: list[tuple[Path, dict]] = []
    for session_file in sorted(phase_dir.glob("*.summary.json")):
        # Skip any prior aggregate to avoid double counting on re-runs
        if session_file.name == "all.summary.json":
            continue
        try:
            with open(session_file) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    parts.append((session_file, data))
        except (OSError, json.JSONDecodeError):
            pass

    if not parts:
        return None

    def _get_counter(data_dict: dict, key: str) -> int:
        c = data_dict.get("counters") or {}
        try:
            return int(c.get(key, 0))
        except (TypeError, ValueError):
            return 0

    total = {
        "tests_run": 0,
        "failures": 0,
        "errors": 0,
        "skips": 0,
    }
    all_rc_zero = True
    component_files: list[str] = []
    for p, d in parts:
        component_files.append(p.name)
        total["tests_run"] += _get_counter(d, "tests_run")
        total["failures"] += _get_counter(d, "failures")
        total["errors"] += _get_counter(d, "errors")
        total["skips"] += _get_counter(d, "skips")
        rc = d.get("returncode")
        try:
            if rc is None or int(rc) != 0:
                all_rc_zero = False
        except (TypeError, ValueError):
            all_rc_zero = False

    aggregate = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "category": category,
        "counters": total,
        "success": bool(all_rc_zero and total["failures"] == 0 and total["errors"] == 0),
        "returncode": 0 if all_rc_zero else 1,
        "components": component_files,
        "summary_file": str((phase_dir / "all.summary.json").resolve()),
    }

    out_path = phase_dir / "all.summary.json"
    try:
        with open(out_path, "w") as f:
            json.dump(aggregate, f, indent=2)
    except OSError:
        return None
    return out_path


_RE_RAN = re.compile(r"\bRan\s+(?P<tests>\d+)\s+tests?\s+in\s+(?P<seconds>[0-9.]+)s\b", re.IGNORECASE)
_RE_FAILED = re.compile(r"FAILED\s*\((?P<parts>[^)]*)\)")
_RE_PART = re.compile(r"\b(?P<key>failures|errors|skipped|expected failures|unexpected successes)\s*=\s*(?P<val>\d+)")


def _maybe_update_summary_counters_from_line(line: str, summary: dict) -> None:
    try:
        # Strip ANSI color codes that may prefix lines in some environments
        ansi_free = re.sub(r"\x1b\[[0-9;]*m", "", line)

        # Heuristic for Odoo logs: count per-test start lines
        # Example: "... odoo.addons...: Starting TestFoo.test_bar ..."
        # Count per-test start lines (relax class name constraint to include JS runners like ProductConnectJSTests)
        if ": Starting " in ansi_free and re.search(r"\b\w+\.test_", ansi_free):
            summary.setdefault("counters", {}).setdefault("tests_run", 0)
            summary["counters"]["tests_run"] += 1

        m = _RE_RAN.search(ansi_free)
        if m:
            tests = int(m.group("tests"))
            summary.setdefault("counters", {}).setdefault("tests_run", 0)
            # Keep the max seen to avoid regressions from noisy lines
            summary["counters"]["tests_run"] = max(summary["counters"]["tests_run"], tests)
            return

        # FAILED (failures=1, errors=0, skipped=2)
        m = _RE_FAILED.search(ansi_free)
        if m:
            parts = m.group("parts")
            for pm in _RE_PART.finditer(parts):
                key = pm.group("key").lower()
                val = int(pm.group("val"))
                if key == "skipped":
                    summary["counters"]["skips"] = val
                elif key == "failures":
                    summary["counters"]["failures"] = val
                elif key == "errors":
                    summary["counters"]["errors"] = val
            return

        # JS runs often log errors as "ERROR: Class.test_method" lines; count them
        if " ERROR: " in ansi_free and re.search(r"\b\w+\.test_", ansi_free):
            summary.setdefault("counters", {}).setdefault("errors", 0)
            summary["counters"]["errors"] += 1
            return

        # OK (skipped=3) — uncommon but handle
        if "OK (" in ansi_free and "skipped=" in ansi_free:
            for pm in _RE_PART.finditer(ansi_free):
                if pm.group("key").lower() == "skipped":
                    summary["counters"]["skips"] = int(pm.group("val"))
                    break
    except (re.error, ValueError):
        pass


def _prune_old_log_sessions(keep: int | None = None) -> None:
    log_root = Path("tmp/test-logs")
    if not log_root.exists():
        return
    try:
        keep = keep or int(get_settings().test_log_keep)
    except ValueError:
        keep = 12
    sessions = sorted([d for d in log_root.iterdir() if d.is_dir() and d.name.startswith("test-")])
    if len(sessions) <= keep:
        return
    to_remove = sessions[:-keep]
    for d in to_remove:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def show_test_stats() -> int:
    all_modules_list = get_our_modules()

    print("Test Statistics for all modules:")
    print("=" * 50)

    grand_total_files = 0
    grand_categories = {
        "unit_test": 0,
        "integration_test": 0,
        "tour_test": 0,
        "validation_test": 0,
    }

    for module in all_modules_list:
        print(f"\nModule: {module}")
        print("-" * 30)

        test_root = Path(f"addons/{module}/tests")
        if not test_root.exists():
            print("  ❌ No tests directory")
            continue

        categories = {
            "unit_test": 0,
            "integration_test": 0,
            "tour_test": 0,
            "validation_test": 0,
        }

        total_files = 0
        for test_file in test_root.rglob("test_*.py"):
            if test_file.name.startswith("test_"):
                total_files += 1
                with open(test_file) as f:
                    content = f.read()
                    if "@tagged(*UNIT_TAGS)" in content or '"unit_test"' in content or "'unit_test'" in content:
                        categories["unit_test"] += 1
                    elif (
                        "@tagged(*INTEGRATION_TAGS)" in content or '"integration_test"' in content or "'integration_test'" in content
                    ):
                        categories["integration_test"] += 1
                    elif "@tagged(*TOUR_TAGS)" in content or '"tour_test"' in content or "'tour_test'" in content:
                        categories["tour_test"] += 1
                    elif "validation" in test_file.name.lower() or '"validation_test"' in content or "'validation_test'" in content:
                        categories["validation_test"] += 1

        print(f"  Total test files: {total_files}")
        for category, count in categories.items():
            print(f"  {category:20}: {count:3} files")
            grand_categories[category] += count

        grand_total_files += total_files

    print("\n" + "=" * 50)
    print("GRAND TOTALS:")
    print(f"Total test files: {grand_total_files}")
    for category, count in grand_categories.items():
        print(f"{category:20}: {count:3} files")

    print("\nTo run tests:")
    print("  uv run test-unit        # Fast unit tests")
    print("  uv run test-integration # Integration tests")
    print("  uv run test-tour        # Browser tours")
    print("  uv run test-all         # All tests")
    print("  uv run test-clean       # Clean up test artifacts")

    # Show recent test logs for agents to easily find
    print("\n" + "=" * 50)
    print("RECENT TEST LOGS:")
    log_dir = Path("tmp/test-logs")
    if log_dir.exists():
        # Get last 5 test runs
        test_dirs = sorted([d for d in log_dir.iterdir() if d.is_dir()], reverse=True)[:5]
        if test_dirs:
            for test_dir in test_dirs:
                summary_file = test_dir / "summary.json"
                if summary_file.exists():
                    try:
                        with open(summary_file) as f:
                            summary = json.load(f)
                            status = "✅ PASSED" if summary.get("success") else "❌ FAILED"
                            if summary.get("timeout"):
                                status = "⏱️ TIMEOUT"
                            test_type = summary.get("test_type", "unknown")
                            elapsed = summary.get("elapsed_seconds", 0)
                            print(f"  {test_dir.name}: {status} ({test_type}, {elapsed:.1f}s)")
                            print(f"    📁 Logs: {test_dir}")
                    except (OSError, json.JSONDecodeError):
                        print(f"  {test_dir.name}: [Could not read summary]")
        else:
            print("  No recent test runs found")
    else:
        print("  No test logs directory found yet")

    return 0


def cleanup_test_databases(production_db: str | None = None) -> None:
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test databases for {production_db}...")

    # Get list of test databases
    ensure_services_up([get_database_service()])
    wait_for_database_ready()
    # Collect both legacy ("_ut_") and standard ("_test_") databases
    db_user = get_db_user()
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            (
                "SELECT datname FROM pg_database "
                f"WHERE datname LIKE '{production_db}_test_%' "
                f"   OR datname LIKE '{production_db}_ut_%';"
            ),
        ],
    )
    if result.returncode != 0:
        print(f"   ⚠️  Could not list databases: {result.stderr}")
        return

    test_dbs = [db.strip() for db in result.stdout.strip().split("\n") if db.strip()]

    if not test_dbs:
        print(f"   No test databases found")
        return

    print(f"   Found {len(test_dbs)} test database(s): {', '.join(test_dbs)}")

    for db in test_dbs:
        # Terminate connections
        _compose_exec(
            get_database_service(),
            [
                "psql",
                "-U",
                db_user,
                "-d",
                "postgres",
                "-c",
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}' AND pid <> pg_backend_pid();",
            ],
        )

        _force_drop_database(db)

    # Verify all gone
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            (
                "SELECT datname FROM pg_database "
                f"WHERE datname LIKE '{production_db}_test_%' "
                f"   OR datname LIKE '{production_db}_ut_%';"
            ),
        ],
    )
    if result.returncode == 0 and not result.stdout.strip():
        print("   ✅ All test databases dropped")


def create_filestore_snapshot(test_db_name: str, production_db: str) -> None:
    root = get_filestore_root().rstrip("/")
    production_filestore = f"{root}/filestore/{production_db}"
    test_filestore = f"{root}/filestore/{test_db_name}"
    script_runner_service = get_script_runner_service()
    ensure_services_up([script_runner_service])

    # Clean target first
    _compose_exec(script_runner_service, ["sh", "-c", f"rm -rf '{test_filestore}' || true"])

    # Try hardlink clone
    result = _compose_exec(
        script_runner_service,
        [
            "sh",
            "-c",
            f"if [ -d '{production_filestore}' ]; then cp -al '{production_filestore}' '{test_filestore}' 2>/dev/null || false; else exit 1; fi",
        ],
    )
    if result.returncode == 0:
        print(f"   ✅ Filestore snapshot (hardlinks): {test_filestore}")
        return

    # Fallback to rsync copy
    result = _compose_exec(
        script_runner_service,
        [
            "sh",
            "-c",
            f"rsync -a --delete '{production_filestore}/' '{test_filestore}/' 2>/dev/null || false",
        ],
    )
    if result.returncode == 0:
        print(f"   ✅ Filestore snapshot (rsync): {test_filestore}")
    else:
        print(f"   ❌ Failed to copy filestore: {result.stderr}")


def cleanup_test_filestores(production_db: str | None = None) -> None:
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test filestores for {production_db}...")

    script_runner_service = get_script_runner_service()
    ensure_services_up([script_runner_service])
    root = get_filestore_root().rstrip("/")
    result = _compose_exec(
        script_runner_service,
        [
            "sh",
            "-c",
            f"ls -d {root}/filestore/{production_db}_test_* 2>/dev/null || true",
        ],
    )
    if not result.stdout.strip():
        print(f"   No test filestores found")
        return

    test_filestores = result.stdout.strip().split("\n")
    print(f"   Found {len(test_filestores)} test filestore(s)")

    for filestore in test_filestores:
        if filestore:
            check_result = _compose_exec(
                script_runner_service,
                [
                    "sh",
                    "-c",
                    f"if [ -L '{filestore}' ]; then echo 'symlink'; elif [ -d '{filestore}' ]; then echo 'directory'; else echo 'unknown'; fi",
                ],
            )
            is_symlink = check_result.stdout.strip() == "symlink"

            if is_symlink:
                result = _compose_exec(script_runner_service, ["rm", filestore])
            else:
                result = _compose_exec(script_runner_service, ["rm", "-rf", filestore])
            if result.returncode == 0:
                filestore_name = filestore.split("/")[-1]
                type_str = "symlink" if is_symlink else "directory"
                print(f"   ✅ Removed {type_str}: {filestore_name}")
            else:
                print(f"   ⚠️  Failed to remove {filestore}: {result.stderr}")


def cleanup_single_test_filestore(db_name: str) -> None:
    script_runner_service = get_script_runner_service()
    ensure_services_up([script_runner_service])
    root = get_filestore_root().rstrip("/")
    target = f"{root}/filestore/{db_name}"
    result = _compose_exec(script_runner_service, ["sh", "-c", f"[ -e '{target}' ] && rm -rf '{target}' || true"])
    if result.returncode == 0:
        print(f"   ✅ Removed filestore (scoped): {db_name}")
    else:
        print(f"   ⚠️  Failed to remove filestore {db_name}: {result.stderr}")


def cleanup_all_test_artifacts() -> None:
    production_db = get_production_db_name()
    print(f"🧹 Complete test cleanup for production database: {production_db}")
    print("=" * 60)

    cleanup_test_databases(production_db)
    cleanup_test_filestores(production_db)

    print("=" * 60)
    print("✅ Test cleanup completed")





def restart_script_runner_with_orphan_cleanup() -> None:
    script_runner_service = get_script_runner_service()
    # Start script-runner and clean orphans to reduce noisy warnings
    subprocess.run(["docker", "compose", "up", "-d", "--remove-orphans", script_runner_service], capture_output=True)


def drop_and_create_test_database(db_name: str) -> None:
    print(f"🗄️  Cleaning up test database: {db_name}")
    # Step 1: Kill active connections to test database
    print(f"   Terminating connections to {db_name}...")

    # First, get the connection count
    db_user = get_db_user()
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )
    if result.returncode == 0:
        connection_count = result.stdout.strip()
        print(f"   Found {connection_count} active connections to {db_name}")

    # Kill the connections
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not kill connections: {result.stderr}")
    else:
        print(f"   Connection termination command executed")

    # Wait a moment for connections to close
    time.sleep(2)

    # Check again
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )
    if result.returncode == 0:
        remaining_count = result.stdout.strip()
        print(f"   {remaining_count} connections remaining after termination")

    # Step 2: Drop database (aggressive)
    _force_drop_database(db_name)

    # Step 3: Verify drop succeeded
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
        ],
    )
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "0":
            print(f"   ✅ Database {db_name} successfully dropped")
        else:
            print(f"   ⚠️  Warning: Database {db_name} may still exist (count: {count})")

    # Step 4: Create fresh database
    print(f"   Creating fresh database {db_name}...")
    if not _create_database(db_name, db_user):
        print("   ❌ Failed to create database")
        return

    # Step 5: Verify creation succeeded
    if _db_exists(db_name, db_user):
        print(f"   ✅ Database {db_name} successfully created")
    else:
        print(f"   ⚠️  Warning: Database creation may have failed")

    # Ensure Postgres is ready to accept connections for the new DB before we
    # launch Odoo; avoids transient "not currently accepting connections" errors
    wait_for_database_ready()
    print(f"🗄️  Database cleanup completed")


def wait_for_database_ready(retries: int = 30, delay: float = 1.0) -> bool:
    database_service = get_database_service()
    db_user = get_db_user()
    for _ in range(retries):
        res = _compose_exec(database_service, ["pg_isready", "-U", db_user, "-d", "postgres"])
        if res.returncode == 0:
            return True
        time.sleep(delay)
    # Last-chance simple query
    res = _compose_exec(database_service, ["psql", "-U", db_user, "-d", "postgres", "-t", "-c", "SELECT 1"])
    return res.returncode == 0


def _psql_exec(db_user: str, sql: str, database: str = "postgres") -> subprocess.CompletedProcess:
    return _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            database,
            "-c",
            sql,
        ],
    )


def _psql_query(db_user: str, sql: str, database: str = "postgres") -> subprocess.CompletedProcess:
    return _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            database,
            "-t",
            "-c",
            sql,
        ],
    )


def _db_exists(db_name: str, db_user: str) -> bool:
    result = _psql_query(db_user, f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';")
    if result.returncode == 0:
        return result.stdout.strip() == "1"
    return False


def _create_database(db_name: str, db_user: str) -> bool:
    res = _psql_exec(db_user, f"CREATE DATABASE {db_name};")
    return res.returncode == 0


def _force_drop_database(db_name: str) -> None:
    database_service = get_database_service()
    db_user = get_db_user()
    print(f"   Dropping database {db_name} (aggressive)...")
    # Prevent new connections
    _compose_exec(
        database_service,
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"REVOKE CONNECT ON DATABASE {db_name} FROM PUBLIC;",
        ],
    )
    _compose_exec(
        database_service,
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"ALTER DATABASE {db_name} WITH ALLOW_CONNECTIONS false;",
        ],
    )
    # Terminate any remaining
    _compose_exec(
        database_service,
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )
    # Try forced drop (Postgres 13+)
    forced = _compose_exec(
        database_service,
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);",
        ],
    )
    if forced.returncode != 0:
        # Fallback plain drop
        _compose_exec(database_service, ["dropdb", "-U", db_user, "--if-exists", db_name])
    # Verify
    chk = _compose_exec(
        database_service,
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
        ],
    )
    if chk.returncode == 0 and chk.stdout.strip() == "0":
        print(f"   ✅ Dropped {db_name}")
    else:
        print(f"   ⚠️  Could not confirm drop of {db_name}")


def setup_test_authentication(db_name: str) -> str:
    # Generate a secure random password
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))

    print(f"   Setting up test authentication...")

    # Compute a proper pbkdf2-sha512 hash using passlib inside the image
    script_runner_service = get_script_runner_service()
    ensure_services_up([script_runner_service])
    hash_cmd = [
        "python",
        "-c",
        f"from passlib.context import CryptContext; ctx=CryptContext(schemes=['pbkdf2_sha512']);print(ctx.hash('{password}'))",
    ]
    hash_res = _compose_exec(script_runner_service, hash_cmd)
    if hash_res.returncode != 0:
        print(f"   ⚠️  Warning: Could not hash password: {hash_res.stderr}")
        hashed = None
    else:
        hashed = hash_res.stdout.strip().splitlines()[-1]

    if hashed:
        # On some versions the hashed value is stored in `password` directly
        sanitized = hashed.replace("'", "''")
        sql = f"UPDATE res_users SET password='{sanitized}' WHERE login='admin';"
    else:
        # Fallback to setting plain text (old behavior) — may not work on new versions
        sql = f"UPDATE res_users SET password = '{password}' WHERE login='admin';"

    result = _compose_exec(
        get_database_service(),
        ["psql", "-U", get_db_user(), "-d", db_name, "-c", sql],
    )
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Failed to update admin password: {result.stderr}")
    else:
        print(f"   ✅ Test authentication configured (admin user)")

    # Set environment variable for this session
    os.environ["ODOO_TEST_PASSWORD"] = password

    return password


def clone_production_database(db_name: str) -> str:
    production_db = get_production_db_name()
    db_user = get_db_user()
    print(f"🗄️  Cloning production database: {production_db} → {db_name}")
    wait_for_database_ready()

    # Ensure test DB is gone first
    _force_drop_database(db_name)

    # Create empty target database
    if not _create_database(db_name, db_user):
        print("   ❌ Failed to create test database")
        return ""

    # Non-disruptive dump/restore
    cmd = f"set -o pipefail; pg_dump -Fc -U {db_user} {production_db} | pg_restore -U {db_user} -d {db_name} --no-owner --role={db_user}"
    result = _compose_exec(get_database_service(), ["bash", "-lc", cmd])
    if result.returncode != 0:
        print(f"   ❌ Dump/restore failed: {result.stderr}")
        return ""

    # Verify creation succeeded
    if _db_exists(db_name, db_user):
        print(f"   ✅ Database {db_name} is ready")
    else:
        print(f"   ⚠️  Warning: Database creation may have failed")

    print(f"🗄️  Database clone completed")

    # Set up test authentication for tour tests
    return setup_test_authentication(db_name)


def run_docker_test_command(
    test_tags: str,
    db_name: str,
    modules_to_install: list[str],
    timeout: int = 300,
    use_production_clone: bool = False,
    cleanup_before: bool = True,
    cleanup_after: bool = True,
    is_tour_test: bool = False,
    is_js_test: bool = False,
    use_module_prefix: bool = True,
    category: str | None = None,
    session_dir: Path | None = None,
) -> int:
    if modules_to_install is None:
        modules_to_install = get_our_modules()

    modules_str = ",".join(modules_to_install)
    script_runner_service = get_script_runner_service()
    production_db = get_production_db_name()
    ensure_services_up([get_database_service(), script_runner_service])

    if is_tour_test or is_js_test:
        print(f"🧪 Running {'JS' if is_js_test else 'TOUR'} tests (HttpCase-based)")
    else:
        print(f"🧪 Running tests: {test_tags}")
    print(f"📦 Modules: {modules_str}")
    print(f"📊 Database: {db_name}")
    print("-" * 60)

    # Cleanup before tests (scoped by default to avoid cross-run interference)
    settings = get_settings()
    if cleanup_before:
        scoped = settings.test_scoped_cleanup
        if scoped:
            print("🧹 Scoped pre-test cleanup...")
            # Drop only the target DB/filestore for this run
            try:
                _force_drop_database(db_name)
            except OSError:
                pass
            cleanup_single_test_filestore(db_name)
        else:
            print("🧹 Pre-test cleanup (global)...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        print("-" * 60)

    restart_script_runner_with_orphan_cleanup()

    test_password = None
    if use_production_clone:
        test_password = clone_production_database(db_name)
        # Create a local snapshot of filestore for tour/integration tests
        if is_tour_test or "tour" in test_tags or "integration" in test_tags:
            print(f"   Preparing filestore snapshot for tests...")
            create_filestore_snapshot(db_name, production_db)
            print(f"   Cleaning up browser processes...")
            kill_browsers_and_zombies()
            print(f"   ✅ Keeping modules installed to preserve production data; will run with -u")
    else:
        drop_and_create_test_database(db_name)

    # Build test tags - optionally scope tags to specific modules using proper Odoo syntax
    # Syntax: [-][tag][/module][:class][.method]
    # For example, restricting tag 'unit_test' to module 'user_name_extended' -> 'unit_test/user_name_extended'

    # Allow targeted override via env TEST_TAGS without breaking defaults.
    # When provided, we do NOT auto-scope to modules (caller is explicit), and we ensure
    # the category tag is present to avoid running the entire Odoo test suite.
    test_tags_override = (settings.test_tags_override or "").strip()
    if test_tags_override:
        # Ensure category tag present based on flags (avoid referencing derived_category here)
        if is_tour_test:
            must_tag = "tour_test"
        elif is_js_test:
            must_tag = "js_test"
        elif test_tags and "integration" in test_tags:
            must_tag = "integration_test"
        else:
            must_tag = "unit_test"
        final_parts = []
        if must_tag and must_tag not in test_tags_override:
            final_parts.append(must_tag)
        final_parts.append(test_tags_override)
        test_tags_final = ",".join(p for p in final_parts if p)
        use_module_prefix = False  # do not rescope explicit specs
        print(f"🎯 Using TEST_TAGS override: {test_tags_final}")
    else:
        if not test_tags:
            # No tags specified, just limit by modules
            # Use '/module' form so only those modules' tests run
            test_tags_final = ",".join([f"/{module}" for module in modules_to_install])
        elif not use_module_prefix:
            # Use tags as-is without scoping to module(s)
            test_tags_final = test_tags
        else:
            # Scope provided tag expression to modules.
            # We only support the common case where the expression is a single positive tag
            # or a simple comma-separated list where the last item is the primary tag to scope.
            parts = [p.strip() for p in test_tags.split(",") if p.strip()]
            if len(parts) == 1 and not parts[0].startswith("-"):
                tag = parts[0]
                test_tags_final = ",".join([f"{tag}/{module}" for module in modules_to_install])
            else:
                # Fallback: attach module scoping to the last positive tag
                primary = next((p for p in reversed(parts) if not p.startswith("-")), parts[-1])
                scoped = [f"{primary}/{module}" for module in modules_to_install]
                # Keep the other parts (excluding the primary we scoped) and add scoped specs
                keep = [p for p in parts if p != primary]
                test_tags_final = ",".join(keep + scoped)

    print(f"🏷️  Final test tags: {test_tags_final}")

    # Use different module flags based on DB strategy
    module_flag = "-u" if use_production_clone else "-i"

    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
    ]

    # Add environment variable for test password if we have one
    if test_password:
        cmd.extend(["-e", f"ODOO_TEST_PASSWORD={test_password}"])

    # Pass through selected debug env vars for JS diagnostics
    for var in ("JS_PRECHECK", "JS_DEBUG"):
        val = os.environ.get(var)
        if val:
            cmd.extend(["-e", f"{var}={val}"])

    # JS/Tour tests: tours run workers=0 for stability; for JS in Odoo 18, we also default to workers=0
    if is_tour_test or is_js_test:
        # For tours, default to workers=0 to improve stability of HttpCase-based flows.
        # For JS (browser_js/hoot) tests, keep a small number of workers (default 2) unless overridden.
        tour_workers_default = int(settings.tour_workers)
        js_workers_default = int(settings.js_workers)

        # Respect optional warmup toggle; enable the same flag for JS tests to pre-warm the server
        # (TourTestCase honors TOUR_WARMUP in setUp to warm endpoints before browser_js navigations.)
        if is_tour_test or is_js_test:
            cmd.extend(["-e", f"TOUR_WARMUP={settings.tour_warmup}"])

        cmd.extend(
            [
                script_runner_service,
                "/odoo/odoo-bin",
                "-d",
                db_name,
                module_flag,
                modules_str,
                "--test-tags",
                test_tags_final,
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                f"--workers={js_workers_default if is_js_test else tour_workers_default}",
                # Odoo 18 no longer accepts --longpolling-port; avoid passing it.
                f"--db-filter=^{db_name}$",
                "--log-level=test",
                "--without-demo=all",
            ]
        )
        # Optionally disable enterprise addons for JS to avoid auto-installing enterprise stack (faster and avoids mismatches)
        # Note: Do not enable dev assets for JS tests. `--dev=all` slows
        # cold starts and triggers 20s websocket navigation timeouts in
        # `browser_js`. Keep it off by default for test reliability.
    else:
        cmd.extend(
            [
                script_runner_service,
                "/odoo/odoo-bin",
                "-d",
                db_name,
                module_flag,
                modules_str,
                "--test-tags",
                test_tags_final,
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",  # Single-threaded for unit/integration tests
                f"--db-filter=^{db_name}$",
                "--log-level=test",
                "--without-demo=all",
            ]
        )

    # Determine category/labels for logging
    derived_category = category or (
        "tour" if is_tour_test else ("js" if is_js_test else ("integration" if "integration" in test_tags else "unit"))
    )
    # Create log directory for this session
    if session_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("tmp/test-logs") / f"test-{ts}"
        timestamp = ts
    else:
        log_dir = session_dir
        # Derive timestamp from session dir name where possible
        name = log_dir.name
        timestamp = name.replace("test-", "") if name.startswith("test-") else datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Put logs inside a per-phase subdirectory for tidiness
    phase_dir = log_dir / derived_category
    phase_dir.mkdir(parents=True, exist_ok=True)
    # Name files by module when running a split/matrix for units
    if use_module_prefix and modules_to_install and len(modules_to_install) == 1:
        base = modules_to_install[0]
    else:
        base = "all"
    log_file = phase_dir / f"{base}.log"
    summary_file = phase_dir / f"{base}.summary.json"

    # Build a redacted command for display/logging
    redacted = []
    i = 0
    secret_prefixes = ("ODOO_TEST_PASSWORD=", "PASSWORD=", "TOKEN=", "KEY=")
    while i < len(cmd):
        part = cmd[i]
        if part == "-e" and i + 1 < len(cmd):
            env_pair = cmd[i + 1]
            for pref in secret_prefixes:
                if env_pair.startswith(pref):
                    env_pair = pref + "***"
                    break
            redacted.extend([part, env_pair])
            i += 2
            continue
        redacted.append(part)
        i += 1

    print(f"🚀 Command: {' '.join(redacted)}")
    print(f"📁 Logs: {phase_dir}")
    print()

    start_time = time.time()

    # Prepare summary data

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "timestamp": timestamp,
        "command": cmd,
        "test_type": "tour" if is_tour_test else "unit/integration",
        "category": derived_category,
        "database": db_name,
        "modules": modules_to_install,
        "test_tags": test_tags_final,
        "timeout": timeout,
        "start_time": start_time,
        "log_file": str(log_file),
        "summary_file": str(summary_file),
        "counters": {  # Filled opportunistically from output; defaults safe for LLMs
            "tests_run": 0,
            "failures": 0,
            "errors": 0,
            "skips": 0,
        },
    }

    try:
        # Run command with output going to both console and log file
        with open(log_file, "w") as f:
            # Write command info to log (redacted)
            f.write(f"Command: {' '.join(redacted)}\n")
            f.write(f"Started: {datetime.now()}\n")
            f.write("=" * 80 + "\n\n")
            f.flush()

            # Use Popen to stream output to both console and file
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            # Track timing for timeout and stall detection
            last_output_time = time.time()
            stall_warnings = 0
            max_stall_warnings = 10
            stall_threshold = 60  # seconds

            # Enhanced stall detection - track repetitive patterns
            recent_lines = []  # Store last 20 lines for pattern detection
            pattern_occurrences = {}  # Count occurrences of similar lines
            last_pattern_check = time.time()
            pattern_check_interval = 60  # Check for patterns every 1 minute

            # Simple progress tracking
            test_count = 0
            current_test = ""
            last_test = ""

            # Adaptive thresholds based on test type (derive from test_tags)
            test_type_lower = test_tags.lower()
            if "tour" in test_type_lower or is_tour_test:
                stall_threshold = 120  # Tours can take longer
                max_stall_warnings = 15
            elif "integration" in test_type_lower:
                stall_threshold = 90
                max_stall_warnings = 12

            result_code = 0
            error_detected = False
            diagnostics: list[str] = []
            reason: str | None = None

            # Stream output with timeout and stall detection
            while True:
                current_time = time.time()

                # Check for overall timeout
                if current_time - start_time > timeout:
                    print(f"\n⏱️ TIMEOUT: Test execution exceeded {timeout} seconds")
                    f.write(f"\n⏱️ TIMEOUT: Test execution exceeded {timeout} seconds\n")
                    safe_terminate_process(process)
                    result_code = -1
                    break

                # Use select to check if data is available (non-blocking)
                try:
                    ready, _, _ = select.select([process.stdout], [], [], 3.0)

                    if ready:
                        line = process.stdout.readline()
                        if not line:  # EOF - process ended
                            break
                        print(line, end="")  # To console
                        f.write(line)  # To file
                        f.flush()
                        last_output_time = current_time
                        stall_warnings = 0  # Reset on new output

                        # Add line to pattern detection buffer
                        recent_lines.append(line.strip())
                        if len(recent_lines) > 20:  # Keep only last 20 lines
                            recent_lines.pop(0)

                        # Detect hard errors that should mark the run as failed
                        lower = line.lower()
                        if (
                            "critical" in lower and "failed to initialize database" in lower
                        ) or "traceback (most recent call last):" in lower:
                            error_detected = True

                        # Opportunistically parse unittest-style counters
                        _maybe_update_summary_counters_from_line(line, summary)

                        # Environment diagnostics
                        if "permission denied" in lower and "docker daemon socket" in lower:
                            diagnostics.append(line.strip())
                            reason = reason or "docker-permission-denied"
                        if "unable to get image 'postgres" in lower:
                            diagnostics.append(line.strip())
                            reason = reason or "docker-image-access"
                        if 'fatal:  database "' in lower and "does not exist" in lower:
                            diagnostics.append(line.strip())
                            reason = reason or "db-missing"
                        if 'could not translate host name "database"' in lower:
                            diagnostics.append(line.strip())
                            reason = reason or "db-host-unavailable"

                        # Check for repetitive patterns periodically
                        if current_time - last_pattern_check > pattern_check_interval:
                            is_repetitive, pattern_desc = detect_repetitive_pattern(recent_lines, pattern_occurrences)
                            if is_repetitive:
                                print(f"\n🔄 REPETITIVE PATTERN DETECTED: {pattern_desc}")
                                print(f"❌ STALLED: Process stuck in repetitive output. Terminating...")
                                f.write(f"\n🔄 REPETITIVE PATTERN DETECTED: {pattern_desc}\n")
                                f.write(f"❌ STALLED: Process stuck in repetitive output. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -3  # New code for pattern-based stall
                                break
                            last_pattern_check = current_time

                        # Enhanced test completion detection
                        test_completion_indicators = [
                            "Test completed successfully",
                            "tests started in",
                            "post-tests in",
                            "failed, 0 error(s) of",
                            "Initiating shutdown",
                        ]

                        if any(indicator in line for indicator in test_completion_indicators):
                            # Test framework signaled completion - start cleanup timer
                            if not hasattr(locals(), "cleanup_start_time"):
                                cleanup_start_time = current_time
                                print(f"\n🧹 Test completion detected. Starting cleanup timer...")
                                f.write(f"\n🧹 Test completion detected. Starting cleanup timer...\n")

                                # For tour tests, immediately kill browsers to prevent websocket hang
                                if is_tour_test:
                                    print(f"🔫 Preemptively killing browser processes...")
                                    f.write(f"🔫 Preemptively killing browser processes...\n")
                                    kill_browsers_and_zombies()

                        # Check cleanup timeout (much shorter than overall timeout)
                        if hasattr(locals(), "cleanup_start_time"):
                            cleanup_elapsed = current_time - cleanup_start_time
                            if cleanup_elapsed > 30:  # 30 seconds max for cleanup
                                print(f"\n❌ CLEANUP HUNG: Process stuck in cleanup for {cleanup_elapsed:.1f}s. Terminating...")
                                f.write(f"\n❌ CLEANUP HUNG: Process stuck in cleanup for {cleanup_elapsed:.1f}s. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -4  # New code for cleanup hang
                                break

                        # Simple test progress tracking
                        if "test_" in line and ("(" in line or ":" in line):
                            # Looks like a test name
                            parts = line.split()
                            for part in parts:
                                if part.startswith("test_") and part != last_test:
                                    test_count += 1
                                    last_test = part
                                    current_test = part.strip("():")
                                    if test_count % 10 == 0:
                                        print(f"\nℹ️  Progress: {test_count} tests started...\n")
                                        f.write(f"\nℹ️  Progress: {test_count} tests started...\n")
                                    break
                    else:
                        # No output available - check for stall
                        if current_time - last_output_time > stall_threshold:
                            stall_warnings += 1
                            test_info = f" (last test: {current_test})" if current_test else ""
                            print(
                                f"\n⚠️  WARNING: No output for {current_time - last_output_time:.1f}s [{stall_warnings}/{max_stall_warnings}]{test_info}"
                            )
                            f.write(
                                f"\n⚠️  WARNING: No output for {current_time - last_output_time:.1f}s [{stall_warnings}/{max_stall_warnings}]{test_info}\n"
                            )

                            if stall_warnings >= max_stall_warnings:
                                print(f"\n❌ STALLED: Process appears stuck. Terminating...")
                                f.write(f"\n❌ STALLED: Process appears stuck. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -2
                                break

                    # Check if process ended
                    poll_result = process.poll()
                    if poll_result is not None:
                        result_code = poll_result
                        break

                except Exception as e:
                    print(f"\n⚠️  Error reading output: {e}")
                    f.write(f"\n⚠️  Error reading output: {e}\n")
                    time.sleep(0.1)
                    continue

            # Get any remaining output
            try:
                for _ in range(100):  # Limit iterations
                    line = process.stdout.readline()
                    if not line:
                        break
                    print(line, end="")
                    f.write(line)
                    f.flush()
            except OSError:
                pass

            # Ensure process is terminated
            if process.poll() is None:
                try:
                    result_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("\n⚠️  Process didn't exit cleanly, forcing termination")
                    f.write("\n⚠️  Process didn't exit cleanly, forcing termination\n")
                    safe_terminate_process(process)
                    result_code = -1

        elapsed = time.time() - start_time

        print(f"\n⏱️  Completed in {elapsed:.2f}s")

        # Honor in-log fatal error detection even if exit code is 0
        if result_code == 0 and summary.get("test_type") in ("unit/integration", "tour") and error_detected:
            result_code = 1

        # Update summary (store redacted command)
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": result_code,
                "success": result_code == 0,
                "timeout": result_code == -1,
                "stalled": result_code == -2,
                "repetitive_pattern": result_code == -3,
                "cleanup_hang": result_code == -4,
                "tests_started": test_count,
                "last_test": current_test if current_test else None,
                "error": None,
                "command": redacted,
                "reason": reason,
                "diagnostics": diagnostics,
            }
        )

        # Cleanup after tests (default behavior)
        if cleanup_after:
            print("-" * 60)
            scoped = settings.test_scoped_cleanup
            if scoped:
                print("🧹 Post-test cleanup (scoped)...")
                try:
                    _force_drop_database(db_name)
                except OSError:
                    pass
                cleanup_single_test_filestore(db_name)
            else:
                print("🧹 Post-test cleanup (global)...")
                cleanup_test_databases(production_db)
                cleanup_test_filestores(production_db)

        # Build failures.json for machine parsing
        try:
            _build_failures_from_log(log_file, summary)
        except OSError:
            pass

        if result_code == 0:
            print("✅ Tests passed!")
            print(f"📄 Logs saved to: {log_file}")
            # Explicit final footer so the last console line always shows status
            print("🟢 Everything is green")
        else:
            print("❌ Tests failed!")
            print(f"📄 Check logs at: {log_file}")
            print("🔴 Overall: NOT GREEN")

        # Save summary for AI agents to parse
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        return result_code

    except subprocess.TimeoutExpired:
        # This should rarely happen now as we handle timeout inline
        elapsed = time.time() - start_time
        print(f"\n❌ Tests timed out after {timeout} seconds")

        # Update summary for timeout
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": -1,
                "success": False,
                "timeout": True,
                "stalled": False,
                "error": f"Timeout after {timeout} seconds",
            }
        )

        # Save summary even on timeout
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"📄 Partial logs saved to: {log_file}")

        # Cleanup on timeout if enabled
        if cleanup_after:
            print("🧹 Cleanup after timeout...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1

    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        # Cleanup on interrupt if enabled
        if cleanup_after:
            print("🧹 Cleanup after interrupt...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1

    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        # Cleanup on error if enabled
        if cleanup_after:
            print("🧹 Cleanup after error...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode(errors="ignore")).hexdigest()[:16]


def _build_failures_from_log(log_path: Path, summary: dict) -> None:
    out_path = Path(summary.get("summary_file", "")).with_name(
        Path(summary.get("summary_file", "")).stem.replace(".summary", "") + ".failures.json"
    )
    if not log_path.exists():
        return
    entries: list[dict] = []
    cur: dict | None = None
    collecting_tb = False
    tb_lines: list[str] = []
    with open(log_path, errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            l = line.strip()
            lw = l.lower()
            # Start of Python traceback
            if l.startswith("Traceback (most recent call last):"):
                collecting_tb = True
                tb_lines = [l]
                if cur is None:
                    cur = {"type": "error", "message": "", "test": None}
                continue
            if collecting_tb:
                if l == "" and tb_lines:
                    # end of traceback chunk
                    cur = cur or {"type": "error", "message": "", "test": None}
                    tb = "\n".join(tb_lines)
                    cur["traceback"] = tb
                    cur["fingerprint"] = _hash_text(tb)
                    entries.append(cur)
                    cur = None
                    tb_lines = []
                    collecting_tb = False
                else:
                    tb_lines.append(l)
                continue
            # Unittest-style headers (avoid logging noise like DB "ERROR:" lines)
            if lw.startswith(("fail:", "error:")):
                parts = l.split(maxsplit=1)
                typ = parts[0].rstrip(":").lower()
                rest = parts[1] if len(parts) > 1 else ""
                # Heuristic: only treat as a unit test header if the rest mentions a test id
                # (contains 'test' token or looks like Class.test or module.Class)
                rest_l = rest.lower()
                if "test" not in rest_l:
                    # Likely an infra log line (e.g., odoo.sql_db ERROR: ...). Ignore.
                    continue
                test_id = rest
                cur = {"type": "fail" if typ == "fail" else "error", "test": test_id, "message": ""}
                continue
            # Short failure lines like AssertionError: ...
            if cur and ("assert" in lw or lw.startswith(("valueerror:", "keyerror:", "typeerror:", "psycopg2"))):
                cur["message"] = l
                # Fallthrough: wait for traceback or finalize if standalone
                continue
            # Finalize on blank after a short error context without traceback
            if cur and l == "":
                entries.append(cur)
                cur = None
                continue
    # Save
    out = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "count": len(entries),
        "entries": entries,
    }
    try:
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        # Link in summary
        summary["failures_file"] = str(out_path)
        summary["failures_count"] = len(entries)
    except OSError:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "unit":
            # Allow optional module list after "unit" to restrict scope
            modules = sys.argv[2:] if len(sys.argv) > 2 else None
            sys.exit(run_unit_tests(modules))
        elif command == "integration":
            sys.exit(run_integration_tests())
        elif command == "tour":
            sys.exit(run_tour_tests())
        elif command == "all":
            sys.exit(run_all_tests())
        elif command == "stats":
            sys.exit(show_test_stats())
        elif command == "clean" or command == "cleanup":
            cleanup_all_test_artifacts()
            sys.exit(0)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        print("Usage: python test_commands.py [unit|integration|tour|all|stats|clean]")
        sys.exit(1)
