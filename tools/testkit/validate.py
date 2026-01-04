import argparse
import json
from pathlib import Path

from .counts import count_js_tests, count_py_tests
from .sharding import discover_modules_with


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _source_counts(addons_root: Path) -> dict[str, int]:
    return {
        "unit": count_py_tests(addons_root.glob("**/tests/unit/**/*.py")),
        "integration": count_py_tests(addons_root.glob("**/tests/integration/**/*.py")),
        "tour": count_py_tests(addons_root.glob("**/tests/tour/**/*.py")),
        "js": count_js_tests(addons_root.rglob("*.test.js")),
    }


def _executed_counts(session_dir: Path) -> dict[str, int]:
    executed_counts: dict[str, int] = {"unit": 0, "js": 0, "integration": 0, "tour": 0}
    summary = _read_json(session_dir / "summary.json") or {}
    results = summary.get("results") or {}
    for phase in executed_counts.keys():
        counters = (results.get(phase) or {}).get("counters") or {}
        try:
            executed_counts[phase] = int(counters.get("tests_run", 0))
        except (ValueError, TypeError):
            executed_counts[phase] = 0
    return executed_counts


def _phase_modules(addons_root: Path, phase: str) -> list[str]:
    patterns = {
        "unit": ["**/tests/unit/**/*.py"],
        "integration": ["**/tests/integration/**/*.py"],
        "tour": ["**/tests/tour/**/*.py"],
        "js": ["static/tests/**/*.test.js"],
    }
    return sorted(discover_modules_with(patterns.get(phase, []), addons_root))


def _executed_modules(session_dir: Path, phase: str) -> list[str]:
    phase_dir = session_dir / phase
    if not phase_dir.exists():
        return []
    modules: set[str] = set()
    for summary_file in phase_dir.glob("*.summary.json"):
        data = _read_json(summary_file) or {}
        for module_name in data.get("modules") or []:
            modules.add(module_name)
    return sorted(modules)


def _failures_summary(session_dir: Path) -> dict[str, dict[str, int]]:
    phase_failures: dict[str, dict[str, int]] = {}
    for phase in ("unit", "js", "integration", "tour"):
        failure_path = session_dir / phase / "all.failures.json"
        failure_data = _read_json(failure_path) or {}
        counts = {"fail": 0, "error": 0, "js_fail": 0}
        for entry in failure_data.get("entries", []):
            failure_type = str(entry.get("type", "fail"))
            if failure_type not in counts:
                counts[failure_type] = 0
            counts[failure_type] += 1
        phase_failures[phase] = counts
    return phase_failures


def validate(session: str | None = None, json_out: bool = False) -> int:
    base_dir = Path("tmp/test-logs")
    session_dir = base_dir / session if session else base_dir / "latest"
    addons_root = Path("addons")

    source_counts = _source_counts(addons_root)
    executed_counts = _executed_counts(session_dir)
    ok_counts = all(
        executed_counts[phase] >= source_counts.get(phase, 0)
        for phase in ("unit", "js", "integration", "tour")
    )

    # Module-level coverage
    missing: dict[str, list[str]] = {}
    for phase in ("unit", "js", "integration", "tour"):
        expected = set(_phase_modules(addons_root, phase))
        executed = set(_executed_modules(session_dir, phase))
        missing[phase] = sorted(expected - executed)
    ok_modules = all(len(missing_modules) == 0 for missing_modules in missing.values())

    failures = _failures_summary(session_dir)

    payload = {
        "session": session_dir.name,
        "source_counts": source_counts,
        "executed_counts": executed_counts,
        "counts_ok": ok_counts,
        "missing_modules": missing,
        "modules_ok": ok_modules,
        "failures": failures,
        "summary": str((session_dir / "summary.json").resolve()),
    }
    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Session: {payload['session']}")
        print("Counts (source vs executed):")
        for phase in ("unit", "js", "integration", "tour"):
            print(f"  {phase:<12} {source_counts[phase]:>5} → {executed_counts[phase]:>5}")
        print(f"Counts OK: {ok_counts}")
        print("Missing modules (have tests but not executed):")
        any_missing = False
        for phase, missing_modules in missing.items():
            if missing_modules:
                any_missing = True
                print(f"  {phase:<12}: {', '.join(missing_modules)}")
        if not any_missing:
            print("  none")
        print("Failures by phase (fail/error/js_fail):")
        for phase, failure_counts in failures.items():
            print(
                f"  {phase:<12}: {failure_counts.get('fail', 0)}/"
                f"{failure_counts.get('error', 0)}/{failure_counts.get('js_fail', 0)}"
            )
        print(f"Summary: {payload['summary']}")

    # Final code: counts and modules must be OK; failures/errors allowed per your policy
    return 0 if (ok_counts and ok_modules) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate that all tests were executed and summarize failures")
    parser.add_argument("--session", default=None, help="Specific session dir name")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)
    return validate(session=args.session, json_out=args.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
