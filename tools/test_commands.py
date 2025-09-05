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

# Summary schema version for all JSON outputs produced by test runner
SUMMARY_SCHEMA_VERSION = "1.0"


def normalize_line_for_pattern_detection(line: str) -> str:
    """Normalize a log line for pattern detection by removing timestamps and variable parts."""

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


def detect_repetitive_pattern(recent_lines: list, pattern_occurrences: dict, min_occurrences: int = 5) -> tuple[bool, str]:
    """
    Detect if we're seeing repetitive patterns in the log output.
    Returns (is_repetitive, pattern_description).
    """
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


def kill_browser_processes() -> None:
    """Aggressively kill browser processes to prevent websocket cleanup hangs."""
    sr = get_script_runner_service()
    ensure_services_up([sr])
    browser_patterns = ["chromium.*headless", "chrome.*headless", "chromium", "chrome", "WebDriver", "geckodriver", "chromedriver"]
    for pattern in browser_patterns:
        try:
            _compose_exec(sr, ["pkill", "-9", "-f", pattern])
        except Exception:
            pass


def safe_terminate_process(process: subprocess.Popen, container_prefix: str = None) -> None:
    """Safely terminate a process with proper cleanup."""
    if container_prefix is None:
        container_prefix = get_container_prefix()

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

        sr = get_script_runner_service()
        for pattern in patterns:
            try:
                _compose_exec(sr, ["pkill", "-f", pattern])
            except Exception:
                pass  # Ignore cleanup failures

    except Exception as e:
        print(f"Error during process termination: {e}")


def get_container_prefix() -> str:
    """Get the Compose project name (container prefix)."""
    return os.environ.get("ODOO_PROJECT_NAME", "odoo")


def get_database_service() -> str:
    return "database"


def get_production_db_name() -> str:
    result = subprocess.run(["docker", "compose", "config", "--format", "json"], capture_output=True, text=True)
    if result.returncode == 0:
        import json

        config = json.loads(result.stdout)
        for service_name, service in config.get("services", {}).items():
            if "web" in service_name.lower():
                env = service.get("environment", {})
                if isinstance(env, dict):
                    return env.get("ODOO_DB_NAME", "odoo")
                elif isinstance(env, list):
                    for env_var in env:
                        if env_var.startswith("ODOO_DB_NAME="):
                            return env_var.split("=", 1)[1]
    return "odoo"


def get_script_runner_service() -> str:
    result = subprocess.run(["docker", "compose", "ps", "--services"], capture_output=True, text=True)
    services = result.stdout.strip().split("\n") if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"


def _compose_exec(service: str, args: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run `docker compose exec -T <service> ...` consistently."""
    cmd = ["docker", "compose", "exec", "-T", service] + args
    return subprocess.run(cmd, capture_output=capture_output, text=True)


def _compose_run(service: str, args: list[str], env: dict | None = None) -> subprocess.Popen:
    """Run `docker compose run --rm <service> ...` and stream output later."""
    cmd = ["docker", "compose", "run", "--rm", service] + args
    if env:
        env_pairs = sum((["-e", f"{k}={v}"] for k, v in env.items()), [])
        cmd = ["docker", "compose", "run", "--rm"] + env_pairs + [service] + args
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)


def ensure_services_up(services: list[str]) -> None:
    """Ensure listed services are started (idempotent)."""
    for s in services:
        subprocess.run(["docker", "compose", "up", "-d", s], capture_output=True)


def load_timeouts() -> dict:
    """Load timeouts from pyproject.toml [tool.odoo-test.timeouts]."""
    try:
        import tomli  # type: ignore

        with open("pyproject.toml", "rb") as f:
            data = tomli.load(f)
        return data.get("tool", {}).get("odoo-test", {}).get("timeouts", {}) or {}
    except Exception:
        return {}


def get_our_modules() -> list[str]:
    modules = []
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
                modules.append(name)
    return modules


def run_unit_tests(modules: list[str] | None = None, *, session_dir: Path | None = None) -> int:
    """Run unit tests.

    If ``modules`` is provided, restrict installation and test tags to that
    subset. This enables focused runs like:

        python -m tools.test_commands unit user_name_extended

    Default behavior (``modules is None``) runs against all custom addons.
    """
    user_scoped = modules is not None and len(modules) > 0
    if user_scoped:
        # Keep only valid modules present in our addons directory
        available = set(get_our_modules())
        modules = [m for m in modules if m in available]
        if not modules:
            print("❌ No matching modules found under ./addons for requested unit test run")
            return 1
    else:
        modules = get_our_modules()

    timeout_cfg = load_timeouts().get("unit", 300)

    # Split-by-module mode to avoid aborting on first failing module
    split = os.environ.get("TEST_UNIT_SPLIT", "1") != "0"
    if not split or (user_scoped and len(modules) == 1):
        test_db_name = f"{get_production_db_name()}_test_unit"
        use_prefix = True if user_scoped else False
        return run_docker_test_command(
            "unit_test",
            test_db_name,
            modules,
            timeout=timeout_cfg,
            use_module_prefix=use_prefix,
            category="unit",
            session_dir=session_dir,
        )

    print("🔀 Unit test matrix: per-module runs to collect all failures")
    overall_rc = 0
    results: list[tuple[str, int, Path]] = []
    for module in modules:
        db = f"{get_production_db_name()}_ut_{module}"
        print("-" * 60)
        print(f"▶️  {module}")
        rc = run_docker_test_command(
            "unit_test",
            db,
            [module],
            timeout=timeout_cfg,
            use_module_prefix=True,
            category="unit",
            session_dir=session_dir,
        )
        # Find the most recent log dir to report back (best-effort)
        try:
            latest_dir = max((d for d in (Path("tmp/test-logs")).iterdir() if d.is_dir()), key=lambda p: p.name)
        except Exception:
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
        except Exception:
            # Non-fatal: logs still exist per-module
            pass

    return 0 if overall_rc == 0 else 1


def run_integration_tests(*, session_dir: Path | None = None) -> int:
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_integration"
    timeout_cfg = load_timeouts().get("integration", 600)
    return run_docker_test_command(
        "integration_test",
        test_db_name,
        modules,
        timeout=timeout_cfg,
        use_production_clone=True,
        use_module_prefix=False,
        category="integration",
        session_dir=session_dir,
    )


def run_tour_tests(*, session_dir: Path | None = None) -> int:
    print("🧪 Starting tour tests...")
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_tour"
    print(f"   Database: {test_db_name}")
    print(f"   Modules: {', '.join(modules)}")
    timeout_cfg = load_timeouts().get("tour", 1800)
    return run_docker_test_command(
        "tour_test",
        test_db_name,
        modules,
        timeout=timeout_cfg,
        use_production_clone=True,
        is_tour_test=True,
        use_module_prefix=False,
        category="tour",
        session_dir=session_dir,
    )


def run_js_tests(modules: list[str] | None = None, *, session_dir: Path | None = None) -> int:
    """Run JS/hoot tests in a browser with dev assets and workers.

    These are HttpCase-based and should not run with workers=0.
    """
    if modules:
        available = set(get_our_modules())
        modules = [m for m in modules if m in available]
        if not modules:
            print("❌ No matching modules found under ./addons for requested JS test run")
            return 1
    else:
        modules = get_our_modules()

    test_db_name = f"{get_production_db_name()}_test_js"
    timeout_cfg = load_timeouts().get("js", 1200)
    return run_docker_test_command(
        "js_test",
        test_db_name,
        modules,
        timeout=timeout_cfg,
        use_production_clone=False,
        is_js_test=True,
        use_module_prefix=False,
        category="js",
        session_dir=session_dir,
    )


def _get_latest_log_summary() -> tuple[Path | None, dict | None]:
    """Return most recent test session directory and its summary.

    Prefers aggregate summary.json at the session root. If absent, falls back
    to the newest per-phase *.summary.json file in that session.
    If TEST_LOG_SESSION is set, uses that directory explicitly.
    """
    log_root = Path("tmp/test-logs")
    if not log_root.exists():
        return None, None

    forced = os.environ.get("TEST_LOG_SESSION")
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
        except Exception:
            pass

    # Fallback to latest per-phase summary (search recursively)
    candidates = sorted(latest.rglob("*.summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        try:
            with open(candidates[0]) as f:
                return latest, json.load(f)
        except Exception:
            return latest, None
    return latest, None


def run_all_tests() -> int:
    """Run all test categories without hanging.

    Runs unit → integration → tour in separate test sessions to avoid
    cross-category interference and long single-run initialization that
    can hang. Each category uses its tuned timeout and cleanup.
    """
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
    except Exception:
        pass
    # Track per-phase return codes and logs for accurate summary
    rc_unit: int | None = None
    rc_js: int | None = None
    rc_integration: int | None = None
    rc_tour: int | None = None
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
    }
    any_fail = any(code is not None and code != 0 for code in (rc_unit, rc_js, rc_integration, rc_tour))
    aggregate["success"] = not any_fail

    # Aggregate counters across phases when available
    def _sum_counter(key: str) -> int:
        total = 0
        for k in ("unit", "js", "integration", "tour"):
            s = aggregate["results"].get(k) or {}
            c = (s.get("counters") or {}) if isinstance(s, dict) else {}
            try:
                total += int(c.get(key, 0))
            except Exception:
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
    except Exception:
        pass

    # Write a simple index.md for quick navigation and update latest symlink
    try:
        _write_session_index(session_dir, aggregate)
        _update_latest_symlink(session_dir)
    except Exception:
        pass

    if not any_fail:
        print("\n✅ All categories passed")
        print(f"📁 Logs: {session_dir}")
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
        # Return first non-zero code for conventional CI semantics
        for code in (rc_unit, rc_js, rc_integration, rc_tour):
            if code and code != 0:
                return code
        return 1


def _write_session_index(session_dir: Path, aggregate: dict) -> None:
    lines: list[str] = []
    lines.append(f"# Test Session {aggregate.get('session', session_dir.name)}")
    ok = aggregate.get("success", False)
    overall = "PASSED" if ok else "FAILED"
    lines.append("")
    lines.append(f"Overall: {overall}")
    lines.append("")
    lines.append("## Phases")
    for cat in ("unit", "js", "integration", "tour"):
        cat_dir = session_dir / cat
        if not cat_dir.exists():
            continue
        entries = []
        for sfile in sorted(cat_dir.glob("*.summary.json")):
            base = sfile.stem.replace(".summary", "")
            log = sfile.with_suffix("").with_suffix(".log")
            entries.append(f"- {cat}: {base} → {sfile.name} / {log.name}")
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
    except Exception:
        pass
    rel = os.path.relpath(session_dir, latest.parent)
    try:
        latest.symlink_to(rel)
    except Exception:
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
            except Exception:
                pass
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _write_digest(session_dir: Path, aggregate: dict) -> None:
    """Write a compact, LLM-friendly digest.json at the session root."""
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
    """Aggregate multiple per-phase *.summary.json files into a single summary.

    Intended for split runs (e.g., unit tests per-module). Sums counters across
    all component summaries and writes an `all.summary.json` file in the phase
    directory so downstream readers (_get_latest_log_summary, run_all_tests)
    see accurate totals.
    """
    phase_dir = session_dir / category
    if not phase_dir.exists():
        return None

    parts: list[tuple[Path, dict]] = []
    for sfile in sorted(phase_dir.glob("*.summary.json")):
        # Skip any prior aggregate to avoid double counting on re-runs
        if sfile.name == "all.summary.json":
            continue
        try:
            with open(sfile) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    parts.append((sfile, data))
        except Exception:
            pass

    if not parts:
        return None

    def _get_counter(d: dict, key: str) -> int:
        c = d.get("counters") or {}
        try:
            return int(c.get(key, 0))
        except Exception:
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
        except Exception:
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
    except Exception:
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
        if ": Starting " in ansi_free and re.search(r"\bTest\w*\.test_", ansi_free):
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

        # OK (skipped=3) — uncommon but handle
        if "OK (" in ansi_free and "skipped=" in ansi_free:
            for pm in _RE_PART.finditer(ansi_free):
                if pm.group("key").lower() == "skipped":
                    summary["counters"]["skips"] = int(pm.group("val"))
                    break
    except Exception:
        pass


def _prune_old_log_sessions(keep: int | None = None) -> None:
    log_root = Path("tmp/test-logs")
    if not log_root.exists():
        return
    try:
        keep = keep or int(os.environ.get("TEST_LOG_KEEP", "12"))
    except ValueError:
        keep = 12
    sessions = sorted([d for d in log_root.iterdir() if d.is_dir() and d.name.startswith("test-")])
    if len(sessions) <= keep:
        return
    to_remove = sessions[:-keep]
    for d in to_remove:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def show_test_stats() -> int:
    modules = get_our_modules()

    print("Test Statistics for all modules:")
    print("=" * 50)

    grand_total_files = 0
    grand_categories = {
        "unit_test": 0,
        "integration_test": 0,
        "tour_test": 0,
        "validation_test": 0,
    }

    for module in modules:
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
                    except:
                        print(f"  {test_dir.name}: [Could not read summary]")
        else:
            print("  No recent test runs found")
    else:
        print("  No test logs directory found yet")

    return 0


def cleanup_test_databases(production_db: str = None) -> None:
    """Drop test databases for this project.

    Historically we created per-module unit DBs as "${PROD}_ut_<module>" and
    other phases as "${PROD}_test_*". Clean up both patterns to avoid orphaned
    databases accumulating between runs.
    """
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test databases for {production_db}...")

    # Get list of test databases
    ensure_services_up([get_database_service()])
    wait_for_database_ready()
    # Collect both legacy ("_ut_") and standard ("_test_") databases
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
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
                "odoo",
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
            "odoo",
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
    """Create a fast read/write test filestore copied from production.

    Strategy:
    - Prefer hardlink copy (cp -al) for speed/space when supported
    - Fallback to rsync -a
    - Avoid symlink production to prevent data mutation during tests
    """
    production_filestore = f"/volumes/data/filestore/{production_db}"
    test_filestore = f"/volumes/data/filestore/{test_db_name}"
    sr = get_script_runner_service()
    ensure_services_up([sr])

    # Clean target first
    _compose_exec(sr, ["sh", "-c", f"rm -rf '{test_filestore}' || true"])

    # Try hardlink clone
    result = _compose_exec(
        sr,
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
        sr,
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


def cleanup_test_filestores(production_db: str = None) -> None:
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test filestores for {production_db}...")

    sr = get_script_runner_service()
    ensure_services_up([sr])
    result = _compose_exec(
        sr,
        [
            "sh",
            "-c",
            f"ls -d /volumes/data/filestore/{production_db}_test_* 2>/dev/null || true",
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
                sr,
                [
                    "sh",
                    "-c",
                    f"if [ -L '{filestore}' ]; then echo 'symlink'; elif [ -d '{filestore}' ]; then echo 'directory'; else echo 'unknown'; fi",
                ],
            )
            is_symlink = check_result.stdout.strip() == "symlink"

            if is_symlink:
                result = _compose_exec(sr, ["rm", filestore])
            else:
                result = _compose_exec(sr, ["rm", "-rf", filestore])
            if result.returncode == 0:
                filestore_name = filestore.split("/")[-1]
                type_str = "symlink" if is_symlink else "directory"
                print(f"   ✅ Removed {type_str}: {filestore_name}")
            else:
                print(f"   ⚠️  Failed to remove {filestore}: {result.stderr}")


def cleanup_all_test_artifacts() -> None:
    """Complete cleanup of all test artifacts"""
    production_db = get_production_db_name()
    print(f"🧹 Complete test cleanup for production database: {production_db}")
    print("=" * 60)

    cleanup_test_databases(production_db)
    cleanup_test_filestores(production_db)

    print("=" * 60)
    print("✅ Test cleanup completed")


def cleanup_chrome_processes() -> None:
    """Kill any lingering Chrome/Chromium processes in script runner container"""
    sr = get_script_runner_service()
    ensure_services_up([sr])
    _compose_exec(sr, ["pkill", "chrome"])  # graceful
    _compose_exec(sr, ["pkill", "chromium"])  # graceful
    _compose_exec(sr, ["pkill", "-9", "chrome"])  # force
    _compose_exec(sr, ["pkill", "-9", "chromium"])  # force
    _compose_exec(sr, ["sh", "-c", "ps aux | grep defunct | awk '{print $2}' | xargs -r kill -9"])  # zombies


def restart_script_runner_with_orphan_cleanup() -> None:
    sr = get_script_runner_service()
    # Start script-runner and clean orphans to reduce noisy warnings
    subprocess.run(["docker", "compose", "up", "-d", "--remove-orphans", sr], capture_output=True)


def drop_and_create_test_database(db_name: str) -> None:
    print(f"🗄️  Cleaning up test database: {db_name}")

    # Step 1: Kill active connections to test database
    print(f"   Terminating connections to {db_name}...")

    # First, get the connection count
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
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
            "odoo",
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
            "odoo",
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
            "odoo",
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
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {db_name};",
        ],
    )
    if result.returncode != 0:
        print(f"   ❌ Failed to create database: {result.stderr}")
        return

    # Step 5: Verify creation succeeded
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
        ],
    )
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "1":
            print(f"   ✅ Database {db_name} successfully created")
        else:
            print(f"   ⚠️  Warning: Database creation may have failed (count: {count})")

    print(f"🗄️  Database cleanup completed")


def wait_for_database_ready(retries: int = 30, delay: float = 1.0) -> bool:
    """Wait until the Postgres service responds to pg_isready/psql.

    Returns True if ready, False if timed out.
    """
    svc = get_database_service()
    for _ in range(retries):
        res = _compose_exec(svc, ["pg_isready", "-U", "odoo", "-d", "postgres"], capture_output=True)
        if res.returncode == 0:
            return True
        time.sleep(delay)
    # Last-chance simple query
    res = _compose_exec(svc, ["psql", "-U", "odoo", "-d", "postgres", "-t", "-c", "SELECT 1"], capture_output=True)
    return res.returncode == 0


def _force_drop_database(db_name: str) -> None:
    """Attempt to drop a database even with active connections.

    Strategy:
    - REVOKE CONNECT, ALTER DATABASE ... ALLOW_CONNECTIONS false
    - Terminate backends
    - DROP DATABASE ... WITH (FORCE)
    - Fallback to dropdb --if-exists
    - Verify count
    """
    svc = get_database_service()
    print(f"   Dropping database {db_name} (aggressive)...")
    # Prevent new connections
    _compose_exec(
        svc,
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"REVOKE CONNECT ON DATABASE {db_name} FROM PUBLIC;",
        ],
    )
    _compose_exec(
        svc,
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"ALTER DATABASE {db_name} WITH ALLOW_CONNECTIONS false;",
        ],
    )
    # Terminate any remaining
    _compose_exec(
        svc,
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )
    # Try forced drop (Postgres 13+)
    forced = _compose_exec(
        svc,
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);",
        ],
    )
    if forced.returncode != 0:
        # Fallback plain drop
        _compose_exec(svc, ["dropdb", "-U", "odoo", "--if-exists", db_name])
    # Verify
    chk = _compose_exec(
        svc,
        [
            "psql",
            "-U",
            "odoo",
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
    """Set up test authentication in the cloned database.

    Generates a secure random password and updates the admin user's password
    in the test database. Returns the generated password.
    """
    # Generate a secure random password
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))

    print(f"   Setting up test authentication...")

    # Compute a proper pbkdf2-sha512 hash using passlib inside the image
    sr = get_script_runner_service()
    ensure_services_up([sr])
    hash_cmd = [
        "python",
        "-c",
        (f"from passlib.context import CryptContext; ctx=CryptContext(schemes=['pbkdf2_sha512']);print(ctx.hash('{password}'))"),
    ]
    hash_res = _compose_exec(sr, hash_cmd)
    if hash_res.returncode != 0:
        print(f"   ⚠️  Warning: Could not hash password: {hash_res.stderr}")
        hashed = None
    else:
        hashed = hash_res.stdout.strip().splitlines()[-1]

    if hashed:
        # On some versions the hashed value is stored in `password` directly
        sql = "UPDATE res_users SET password='{}' WHERE login='admin';".format(hashed.replace("'", "''"))
    else:
        # Fallback to setting plain text (old behavior) — may not work on new versions
        sql = f"UPDATE res_users SET password = '{password}' WHERE login='admin';"

    result = _compose_exec(
        get_database_service(),
        ["psql", "-U", "odoo", "-d", db_name, "-c", sql],
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
    print(f"🗄️  Cloning production database: {production_db} → {db_name}")
    wait_for_database_ready()

    # Step 1: Kill active connections to test database
    print(f"   Terminating connections to {db_name}...")

    # First, get the connection count
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
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
            "odoo",
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
    import time

    time.sleep(2)

    # Check again
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
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

    # Step 2: Drop existing test database (aggressive)
    _force_drop_database(db_name)

    # Step 3: Terminate connections to production database before cloning
    print(f"   Terminating connections to production database {production_db}...")
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{production_db}' AND pid <> pg_backend_pid();",
        ],
    )
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not kill production connections: {result.stderr}")
    else:
        print(f"   Production connection termination executed")

    # Wait for connections to close
    time.sleep(2)

    # Step 4: Clone from production database
    print(f"   Cloning from production database {production_db}...")
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {db_name} WITH TEMPLATE {production_db};",
        ],
    )
    if result.returncode != 0:
        print(f"   ❌ Failed to clone database: {result.stderr}")
        return ""

    # Step 4: Verify creation succeeded
    result = _compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
        ],
    )
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "1":
            print(f"   ✅ Database {db_name} successfully cloned from {production_db}")
        else:
            print(f"   ⚠️  Warning: Database creation may have failed (count: {count})")

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

    # Cleanup before tests (default behavior)
    if cleanup_before:
        print("🧹 Pre-test cleanup...")
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
            print(f"   Cleaning up Chrome processes...")
            cleanup_chrome_processes()
            print(f"   ✅ Keeping modules installed to preserve production data; will run with -u")
    else:
        drop_and_create_test_database(db_name)

    # Build test tags - optionally scope tags to specific modules using proper Odoo syntax
    # Syntax: [-][tag][/module][:class][.method]
    # For example, restricting tag 'unit_test' to module 'user_name_extended' -> 'unit_test/user_name_extended'
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

    # JS/Tour tests need workers and dev assets
    if is_tour_test or is_js_test:
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
                f"--workers={int(os.environ.get('TOUR_WORKERS', '2'))}",
                f"--db-filter=^{db_name}$",
                "--log-level=test",
                "--without-demo=all",
            ]
        )
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
                                    kill_browser_processes()

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
            except:
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
            print("🧹 Post-test cleanup...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)

        # Build failures.json for machine parsing
        try:
            _build_failures_from_log(log_file, summary)
        except Exception:
            pass

        if result_code == 0:
            print("✅ Tests passed!")
            print(f"📄 Logs saved to: {log_file}")
        else:
            print("❌ Tests failed!")
            print(f"📄 Check logs at: {log_file}")

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

    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _build_failures_from_log(log_path: Path, summary: dict) -> None:
    """Parse a test log and emit failures.json next to the summary.

    Extracts compact entries with type (fail/error), test id if seen, brief
    message, and a traceback fingerprint.
    """
    out_path = Path(summary.get("summary_file", "")).with_name(
        Path(summary.get("summary_file", "")).stem.replace(".summary", "") + ".failures.json"
    )
    if not log_path.exists():
        return
    entries: list[dict] = []
    cur: dict | None = None
    collecting_tb = False
    tb_lines: list[str] = []
    with open(log_path, "r", errors="ignore") as f:
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
            # Unittest headers
            if lw.startswith(("fail:", "error:")):
                parts = l.split(None, 1)
                typ = parts[0].rstrip(":").lower()
                test_id = parts[1] if len(parts) > 1 else None
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
    except Exception:
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
