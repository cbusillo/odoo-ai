import json
import logging
import os
import time
import xml.etree.ElementTree as element_tree
from datetime import datetime
from pathlib import Path
from typing import Any

from .failures import parse_failures
from .settings import SUMMARY_SCHEMA_VERSION

_logger = logging.getLogger(__name__)


def load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.debug("reporter: failed to read %s (%s)", path, exc)
        return None
    return data if isinstance(data, dict) else None


def write_latest_json(session_dir: Path) -> None:
    latest_json = Path("tmp/test-logs") / "latest.json"
    data = {"schema_version": SUMMARY_SCHEMA_VERSION, "latest": str(session_dir)}
    latest_json.write_text(json.dumps(data, indent=2))


def update_latest_symlink(session_dir: Path) -> None:
    latest = Path("tmp/test-logs") / "latest"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
    except OSError as exc:
        _logger.debug("reporter: failed to unlink latest (%s)", exc)
    rel = os.path.relpath(session_dir, latest.parent)
    try:
        latest.symlink_to(rel)
    except OSError:
        latest.with_suffix(".json").write_text(
            json.dumps({"schema_version": SUMMARY_SCHEMA_VERSION, "latest": str(session_dir)}, indent=2)
        )


def write_manifest(session_dir: Path) -> None:
    manifest: dict[str, Any] = {"schema_version": SUMMARY_SCHEMA_VERSION, "files": []}
    for p in session_dir.rglob("*"):
        if p.is_file():
            try:
                stat = p.stat()
                manifest["files"].append(
                    {
                        "path": str(p.relative_to(session_dir)),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )
            except (OSError, ValueError):
                continue
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def write_session_index(session_dir: Path, aggregate: dict) -> None:
    ok = bool(aggregate.get("success", False))
    lines = [
        f"# Test Session {aggregate.get('session', session_dir.name)}",
        "",
        f"Overall: {'PASSED' if ok else 'FAILED'}",
        "",
        "## Phases",
        "",
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
            lines.extend([f"### {cat.title()}", ""])
            lines.extend(entries)
            lines.append("")
    (session_dir / "index.md").write_text("\n".join(lines))


def write_digest(session_dir: Path, aggregate: dict) -> None:
    # Minimal copy used by bots to scan results quickly
    digest = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "session": aggregate.get("session"),
        "success": bool(aggregate.get("success")),
        "counters_total": aggregate.get("counters_total") or {},
        "return_codes": aggregate.get("return_codes") or {},
        "summary": str((session_dir / "summary.json").resolve()),
    }
    (session_dir / "digest.json").write_text(json.dumps(digest, indent=2))


def begin_session_dir() -> tuple[Path, str, float]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"test-{ts}"
    session_dir = Path("tmp/test-logs") / name
    session_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    return session_dir, name, started


def aggregate_phase(session_dir: Path, phase: str) -> dict | None:
    phase_dir = session_dir / phase
    if not phase_dir.exists():
        return None
    summaries = list(phase_dir.glob("*.summary.json"))
    if not summaries:
        return None
    counters = {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0}
    success = True
    merged_failures: list[dict] = []
    for sf in summaries:
        data = load_json(sf)
        if data is None:
            continue
        c = data.get("counters") or {}
        for k in counters:
            try:
                counters[k] += int(c.get(k, 0))
            except (ValueError, TypeError):
                continue
        success = success and bool(data.get("success", False))
        # parse failures from corresponding log
        log = data.get("log_file")
        if log:
            merged_failures.extend(parse_failures(Path(log)))
    aggregate = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "phase": phase,
        "success": success,
        "counters": counters,
        "shards": len(summaries),
    }
    (phase_dir / "all.summary.json").write_text(json.dumps(aggregate, indent=2))
    (phase_dir / "all.failures.json").write_text(json.dumps({"entries": merged_failures}, indent=2))
    return aggregate


def _map_failure_type_to_junit(failure_type: str) -> str:
    if failure_type == "error":
        return "error"
    return "failure"


def _int_from_counter(counters: dict[str, Any], key: str) -> int:
    raw = counters.get(key, 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _junit_counts(counters: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    tests = _int_from_counter(counters, "tests_run")
    fail_count = sum(1 for entry in entries if _map_failure_type_to_junit(str(entry.get("type", ""))) == "failure")
    err_count = sum(1 for entry in entries if _map_failure_type_to_junit(str(entry.get("type", ""))) == "error")
    if tests == 0:
        tests = fail_count + err_count
    skipped = _int_from_counter(counters, "skips")
    return tests, fail_count, err_count, skipped


def _append_junit_failures(suite: element_tree.Element, entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        name = entry.get("test") or entry.get("fingerprint") or "unknown"
        tc = element_tree.SubElement(suite, "testcase", attrib={"name": str(name)})
        mapped = _map_failure_type_to_junit(str(entry.get("type", "")))
        message = entry.get("message") or entry.get("type") or ""
        el = element_tree.SubElement(tc, mapped, attrib={"message": str(message)})
        tb = entry.get("traceback")
        if tb:
            el.text = str(tb)


def write_junit_for_phase(session_dir: Path, phase: str) -> Path | None:
    phase_dir = session_dir / phase
    agg_path = phase_dir / "all.summary.json"
    if not agg_path.exists():
        return None
    agg = load_json(agg_path)
    if agg is None:
        return None
    failures_path = phase_dir / "all.failures.json"
    failures_data = load_json(failures_path) or {}
    failure_entries: list[dict] = failures_data.get("entries") or []

    counters = agg.get("counters") or {}
    tests, fail_count, err_count, skipped = _junit_counts(counters, failure_entries)

    suite = element_tree.Element(
        "testsuite",
        attrib={
            "name": f"{phase}",
            "tests": str(tests),
            "failures": str(fail_count),
            "errors": str(err_count),
            "skipped": str(skipped),
        },
    )
    _append_junit_failures(suite, failure_entries)

    tree = element_tree.ElementTree(suite)
    out = phase_dir / "junit.xml"
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


def write_junit_root(session_dir: Path) -> Path:
    suites = element_tree.Element("testsuites")
    total_tests = total_fail = total_err = total_skip = 0
    for phase in ("unit", "js", "integration", "tour"):
        junit_path = session_dir / phase / "junit.xml"
        if not junit_path.exists():
            continue
        try:
            tree = element_tree.parse(str(junit_path))
            suite = tree.getroot()
        except (OSError, element_tree.ParseError) as exc:
            _logger.debug("reporter: failed to parse junit %s (%s)", junit_path, exc)
            continue
        suites.append(suite)
        total_tests += int(suite.attrib.get("tests", 0))
        total_fail += int(suite.attrib.get("failures", 0))
        total_err += int(suite.attrib.get("errors", 0))
        total_skip += int(suite.attrib.get("skipped", 0))

    suites.attrib.update(
        {
            "tests": str(total_tests),
            "failures": str(total_fail),
            "errors": str(total_err),
            "skipped": str(total_skip),
        }
    )
    out = session_dir / "junit.xml"
    element_tree.ElementTree(suites).write(out, encoding="utf-8", xml_declaration=True)
    return out


def write_junit_for_shard(summary_file: Path, log_file: Path) -> Path | None:
    data = load_json(summary_file)
    if data is None:
        return None
    counters = data.get("counters") or {}
    failures = parse_failures(log_file)
    tests, fail_count, err_count, skipped = _junit_counts(counters, failures)

    suite = element_tree.Element(
        "testsuite",
        attrib={
            "name": Path(summary_file).stem.replace(".summary", ""),
            "tests": str(tests),
            "failures": str(fail_count),
            "errors": str(err_count),
            "skipped": str(skipped),
        },
    )
    _append_junit_failures(suite, failures)

    out = summary_file.with_suffix("").with_suffix(".junit.xml")
    element_tree.ElementTree(suite).write(out, encoding="utf-8", xml_declaration=True)
    return out


def update_weight_cache_from_session(session_dir: Path, cache_path: Path | None = None) -> None:
    if cache_path is None:
        cache_path = Path("tmp/test-logs/weights.json")
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("reporter: failed to load weight cache (%s)", exc)
        cache = {}

    for phase in ("unit", "js", "integration", "tour"):
        phase_dir = session_dir / phase
        if not phase_dir.exists():
            continue
        for sf in phase_dir.glob("*.summary.json"):
            data = load_json(sf)
            if data is None:
                continue
            secs = float(data.get("elapsed_seconds") or 0.0)
            mods = data.get("modules") or []
            if not secs or not mods:
                continue
            per = secs / max(1, len(mods))
            ph = cache.setdefault(phase, {})
            for m in mods:
                rec = ph.setdefault(m, {"avg_secs": 0.0, "count": 0, "last_secs": 0.0})
                c = int(rec.get("count", 0))
                avg = float(rec.get("avg_secs", 0.0))
                new_avg = (avg * c + per) / (c + 1)
                rec.update({"avg_secs": new_avg, "count": c + 1, "last_secs": per})

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    except OSError as exc:
        _logger.debug("reporter: failed to write weight cache (%s)", exc)


def prune_old_sessions(log_root: Path, keep: int) -> None:
    try:
        sessions = [d for d in log_root.iterdir() if d.is_dir() and d.name.startswith("test-")]
    except OSError:
        return
    if len(sessions) <= keep:
        return
    for p in sorted(sessions, key=lambda p: p.name)[:-keep]:
        try:
            # best-effort recursive removal
            for sub in sorted(p.rglob("*"), reverse=True):
                if sub.is_file() or sub.is_symlink():
                    sub.unlink(missing_ok=True)
                elif sub.is_dir():
                    sub.rmdir()
            p.rmdir()
        except OSError as exc:
            _logger.debug("reporter: failed to prune session %s (%s)", p, exc)
