import json
import logging
import os
import time
import xml.etree.ElementTree as ElementTree
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
    latest_link = Path("tmp/test-logs") / "latest"
    try:
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
    except OSError as exc:
        _logger.debug("reporter: failed to unlink latest (%s)", exc)
    relative_path = os.path.relpath(session_dir, latest_link.parent)
    try:
        latest_link.symlink_to(relative_path)
    except OSError:
        latest_link.with_suffix(".json").write_text(
            json.dumps({"schema_version": SUMMARY_SCHEMA_VERSION, "latest": str(session_dir)}, indent=2)
        )


def write_manifest(session_dir: Path) -> None:
    manifest: dict[str, Any] = {"schema_version": SUMMARY_SCHEMA_VERSION, "files": []}
    for file_path in session_dir.rglob("*"):
        if file_path.is_file():
            try:
                file_stat = file_path.stat()
                manifest["files"].append(
                    {
                        "path": str(file_path.relative_to(session_dir)),
                        "size": file_stat.st_size,
                        "mtime": file_stat.st_mtime,
                    }
                )
            except (OSError, ValueError):
                continue
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def write_session_index(session_dir: Path, aggregate: dict) -> None:
    is_success = bool(aggregate.get("success", False))
    lines = [
        f"# Test Session {aggregate.get('session', session_dir.name)}",
        "",
        f"Overall: {'PASSED' if is_success else 'FAILED'}",
        "",
        "## Phases",
        "",
    ]
    for phase_name in ("unit", "js", "integration", "tour"):
        phase_dir = session_dir / phase_name
        if not phase_dir.exists():
            continue
        phase_entries = []
        for session_file in sorted(phase_dir.glob("*.summary.json")):
            shard_name = session_file.stem.replace(".summary", "")
            log_file = session_file.with_suffix("").with_suffix(".log")
            phase_entries.append(f"- {phase_name}: {shard_name} → {session_file.name} / {log_file.name}")
        if phase_entries:
            lines.extend([f"### {phase_name.title()}", ""])
            lines.extend(phase_entries)
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"test-{timestamp}"
    session_dir = Path("tmp/test-logs") / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    return session_dir, session_name, started_at


def aggregate_phase(session_dir: Path, phase: str) -> dict | None:
    phase_dir = session_dir / phase
    if not phase_dir.exists():
        return None
    summary_files = list(phase_dir.glob("*.summary.json"))
    if not summary_files:
        return None
    counter_totals = {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0}
    all_successful = True
    merged_failure_entries: list[dict] = []
    for summary_file in summary_files:
        summary_data = load_json(summary_file)
        if summary_data is None:
            continue
        counter_values = summary_data.get("counters") or {}
        for counter_name in counter_totals:
            try:
                counter_totals[counter_name] += int(counter_values.get(counter_name, 0))
            except (ValueError, TypeError):
                continue
        all_successful = all_successful and bool(summary_data.get("success", False))
        # parse failures from corresponding log
        log_file = summary_data.get("log_file")
        if log_file:
            merged_failure_entries.extend(parse_failures(Path(log_file)))
    aggregate_data = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "phase": phase,
        "success": all_successful,
        "counters": counter_totals,
        "shards": len(summary_files),
    }
    (phase_dir / "all.summary.json").write_text(json.dumps(aggregate_data, indent=2))
    (phase_dir / "all.failures.json").write_text(json.dumps({"entries": merged_failure_entries}, indent=2))
    return aggregate_data


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
    tests_count = _int_from_counter(counters, "tests_run")
    failure_count = sum(
        1 for entry in entries if _map_failure_type_to_junit(str(entry.get("type", ""))) == "failure"
    )
    error_count = sum(1 for entry in entries if _map_failure_type_to_junit(str(entry.get("type", ""))) == "error")
    if tests_count == 0:
        tests_count = failure_count + error_count
    skipped_count = _int_from_counter(counters, "skips")
    return tests_count, failure_count, error_count, skipped_count


def _append_junit_failures(suite: ElementTree.Element, entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        test_name = entry.get("test") or entry.get("fingerprint") or "unknown"
        testcase_element = ElementTree.SubElement(suite, "testcase", attrib={"name": str(test_name)})
        junit_failure_type = _map_failure_type_to_junit(str(entry.get("type", "")))
        failure_message = entry.get("message") or entry.get("type") or ""
        failure_element = ElementTree.SubElement(
            testcase_element,
            junit_failure_type,
            attrib={"message": str(failure_message)},
        )
        traceback_text = entry.get("traceback")
        if traceback_text:
            failure_element.text = str(traceback_text)


def write_junit_for_phase(session_dir: Path, phase: str) -> Path | None:
    phase_dir = session_dir / phase
    aggregate_path = phase_dir / "all.summary.json"
    if not aggregate_path.exists():
        return None
    aggregate_data = load_json(aggregate_path)
    if aggregate_data is None:
        return None
    failures_path = phase_dir / "all.failures.json"
    failures_data = load_json(failures_path) or {}
    failure_entries: list[dict] = failures_data.get("entries") or []

    counters = aggregate_data.get("counters") or {}
    tests_count, failure_count, error_count, skipped_count = _junit_counts(counters, failure_entries)

    suite_element = ElementTree.Element(
        "testsuite",
        attrib={
            "name": f"{phase}",
            "tests": str(tests_count),
            "failures": str(failure_count),
            "errors": str(error_count),
            "skipped": str(skipped_count),
        },
    )
    _append_junit_failures(suite_element, failure_entries)

    suite_tree = ElementTree.ElementTree(suite_element)
    output_path = phase_dir / "junit.xml"
    suite_tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def write_junit_root(session_dir: Path) -> Path:
    suites_root = ElementTree.Element("testsuites")
    total_tests = total_fail = total_err = total_skip = 0
    for phase in ("unit", "js", "integration", "tour"):
        junit_path = session_dir / phase / "junit.xml"
        if not junit_path.exists():
            continue
        try:
            suite_tree = ElementTree.parse(str(junit_path))
            suite_element = suite_tree.getroot()
        except (OSError, ElementTree.ParseError) as exc:
            _logger.debug("reporter: failed to parse junit %s (%s)", junit_path, exc)
            continue
        suites_root.append(suite_element)
        total_tests += int(suite_element.attrib.get("tests", 0))
        total_fail += int(suite_element.attrib.get("failures", 0))
        total_err += int(suite_element.attrib.get("errors", 0))
        total_skip += int(suite_element.attrib.get("skipped", 0))

    suites_root.attrib.update(
        {
            "tests": str(total_tests),
            "failures": str(total_fail),
            "errors": str(total_err),
            "skipped": str(total_skip),
        }
    )
    output_path = session_dir / "junit.xml"
    ElementTree.ElementTree(suites_root).write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def write_junit_for_shard(summary_file: Path, log_file: Path) -> Path | None:
    summary_data = load_json(summary_file)
    if summary_data is None:
        return None
    counters = summary_data.get("counters") or {}
    failure_entries = parse_failures(log_file)
    tests_count, failure_count, error_count, skipped_count = _junit_counts(counters, failure_entries)

    suite_element = ElementTree.Element(
        "testsuite",
        attrib={
            "name": Path(summary_file).stem.replace(".summary", ""),
            "tests": str(tests_count),
            "failures": str(failure_count),
            "errors": str(error_count),
            "skipped": str(skipped_count),
        },
    )
    _append_junit_failures(suite_element, failure_entries)

    output_path = summary_file.with_suffix("").with_suffix(".junit.xml")
    ElementTree.ElementTree(suite_element).write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def update_weight_cache_from_session(session_dir: Path, cache_path: Path | None = None) -> None:
    if cache_path is None:
        cache_path = Path("tmp/test-logs/weights.json")
    try:
        weight_cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("reporter: failed to load weight cache (%s)", exc)
        weight_cache = {}

    for phase in ("unit", "js", "integration", "tour"):
        phase_dir = session_dir / phase
        if not phase_dir.exists():
            continue
        for summary_file in phase_dir.glob("*.summary.json"):
            summary_data = load_json(summary_file)
            if summary_data is None:
                continue
            elapsed_seconds = float(summary_data.get("elapsed_seconds") or 0.0)
            module_names = summary_data.get("modules") or []
            if not elapsed_seconds or not module_names:
                continue
            per_module_seconds = elapsed_seconds / max(1, len(module_names))
            phase_cache = weight_cache.setdefault(phase, {})
            for module_name in module_names:
                module_record = phase_cache.setdefault(
                    module_name,
                    {"avg_secs": 0.0, "count": 0, "last_secs": 0.0},
                )
                record_count = int(module_record.get("count", 0))
                average_seconds = float(module_record.get("avg_secs", 0.0))
                new_average_seconds = (average_seconds * record_count + per_module_seconds) / (record_count + 1)
                module_record.update(
                    {
                        "avg_secs": new_average_seconds,
                        "count": record_count + 1,
                        "last_secs": per_module_seconds,
                    }
                )

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(weight_cache, indent=2))
    except OSError as exc:
        _logger.debug("reporter: failed to write weight cache (%s)", exc)


def prune_old_sessions(log_root: Path, keep: int) -> None:
    try:
        session_dirs = [
            session_dir for session_dir in log_root.iterdir() if
            session_dir.is_dir() and session_dir.name.startswith("test-")
        ]
    except OSError:
        return
    if len(session_dirs) <= keep:
        return
    for session_dir in sorted(session_dirs, key=lambda session_dir: session_dir.name)[:-keep]:
        try:
            # best-effort recursive removal
            for entry in sorted(session_dir.rglob("*"), reverse=True):
                if entry.is_file() or entry.is_symlink():
                    entry.unlink(missing_ok=True)
                elif entry.is_dir():
                    entry.rmdir()
            session_dir.rmdir()
        except OSError as exc:
            _logger.debug("reporter: failed to prune session %s (%s)", session_dir, exc)
