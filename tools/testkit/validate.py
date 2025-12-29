from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _source_counts(addons_root: Path) -> dict[str, int]:
    def count_py(glob: str) -> int:
        total = 0
        for p in addons_root.glob(glob):
            if not p.is_file():
                continue
            try:
                txt = p.read_text(errors="ignore")
            except Exception:
                continue
            total += len(re.findall(r"^\s*def\s+test_", txt, flags=re.MULTILINE))
        return total

    def count_js() -> int:
        total = 0
        for p in addons_root.rglob("*.test.js"):
            if not p.is_file():
                continue
            try:
                txt = p.read_text(errors="ignore")
            except Exception:
                continue
            total += len(re.findall(r"\btest\s*\(", txt))
        return total

    return {
        "unit": count_py("**/tests/unit/**/*.py"),
        "integration": count_py("**/tests/integration/**/*.py"),
        "tour": count_py("**/tests/tour/**/*.py"),
        "js": count_js(),
    }


def _executed_counts(session_dir: Path) -> dict[str, int]:
    out: dict[str, int] = {"unit": 0, "js": 0, "integration": 0, "tour": 0}
    summary = _read_json(session_dir / "summary.json") or {}
    results = summary.get("results") or {}
    for ph in out.keys():
        c = (results.get(ph) or {}).get("counters") or {}
        try:
            out[ph] = int(c.get("tests_run", 0))
        except Exception:
            out[ph] = 0
    return out


def _phase_modules(addons_root: Path, phase: str) -> list[str]:
    patterns = {
        "unit": ["**/tests/unit/**/*.py"],
        "integration": ["**/tests/integration/**/*.py"],
        "tour": ["**/tests/tour/**/*.py"],
        "js": ["static/tests/**/*.test.js"],
    }
    seen: set[str] = set()
    for module_dir in addons_root.iterdir():
        if not module_dir.is_dir() or not (module_dir / "__manifest__.py").exists():
            continue
        pats = patterns.get(phase, [])
        for pat in pats:
            if list(module_dir.glob(pat)):
                seen.add(module_dir.name)
                break
    return sorted(seen)


def _executed_modules(session_dir: Path, phase: str) -> list[str]:
    ph_dir = session_dir / phase
    if not ph_dir.exists():
        return []
    mods: set[str] = set()
    for sf in ph_dir.glob("*.summary.json"):
        data = _read_json(sf) or {}
        for m in data.get("modules") or []:
            mods.add(m)
    return sorted(mods)


def _failures_summary(session_dir: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for ph in ("unit", "js", "integration", "tour"):
        p = session_dir / ph / "all.failures.json"
        d = _read_json(p) or {}
        counts = {"fail": 0, "error": 0, "js_fail": 0}
        for e in d.get("entries", []):
            t = str(e.get("type", "fail"))
            if t not in counts:
                counts[t] = 0
            counts[t] += 1
        out[ph] = counts
    return out


def validate(session: str | None = None, json_out: bool = False) -> int:
    base = Path("tmp/test-logs")
    session_dir = base / session if session else base / "latest"
    addons_root = Path("addons")

    src = _source_counts(addons_root)
    execd = _executed_counts(session_dir)
    ok_counts = all(execd[k] >= src.get(k, 0) for k in ("unit", "js", "integration", "tour"))

    # Module-level coverage
    missing: dict[str, list[str]] = {}
    for ph in ("unit", "js", "integration", "tour"):
        expected = set(_phase_modules(addons_root, ph))
        got = set(_executed_modules(session_dir, ph))
        missing[ph] = sorted(expected - got)
    ok_modules = all(len(v) == 0 for v in missing.values())

    fails = _failures_summary(session_dir)

    payload = {
        "session": session_dir.name,
        "source_counts": src,
        "executed_counts": execd,
        "counts_ok": ok_counts,
        "missing_modules": missing,
        "modules_ok": ok_modules,
        "failures": fails,
        "summary": str((session_dir / "summary.json").resolve()),
    }
    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Session: {payload['session']}")
        print("Counts (source vs executed):")
        for ph in ("unit", "js", "integration", "tour"):
            print(f"  {ph:<12} {src[ph]:>5} → {execd[ph]:>5}")
        print(f"Counts OK: {ok_counts}")
        print("Missing modules (have tests but not executed):")
        any_missing = False
        for ph, mods in missing.items():
            if mods:
                any_missing = True
                print(f"  {ph:<12}: {', '.join(mods)}")
        if not any_missing:
            print("  none")
        print("Failures by phase (fail/error/js_fail):")
        for ph, c in fails.items():
            print(f"  {ph:<12}: {c.get('fail', 0)}/{c.get('error', 0)}/{c.get('js_fail', 0)}")
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
