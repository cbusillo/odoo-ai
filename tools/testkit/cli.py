from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from shutil import disk_usage
from typing import cast

import click

from .db import db_capacity
from .phases import PhaseOutcome
from .reporter import read_json_file
from .session import PhaseName, TestSession
from .settings import TestSettings
from .sharding import plan_shards_for_phase


def _emit_bottomline(latest: Path, as_json: bool) -> int:
    p = latest / "summary.json"
    if not p.exists():
        if as_json:
            print(json.dumps({"status": "no_summary"}))
        else:
            click.echo("no_summary")
        return 2
    data = read_json_file(p)
    if data is None:
        if as_json:
            print(json.dumps({"status": "invalid"}))
        else:
            click.echo("invalid")
        return 3
    ok = bool(data.get("success"))
    total = data.get("counters_total") or {}
    rcodes = data.get("return_codes") or {}
    out = {
        "success": ok,
        "tests_run": total.get("tests_run"),
        "failures": total.get("failures"),
        "errors": total.get("errors"),
        "skips": total.get("skips"),
        "return_codes": rcodes,
        "session": data.get("session"),
        "summary": str(p.resolve()),
    }
    if as_json:
        print(json.dumps(out))
    else:
        click.echo(
            f"success={out['success']} tests_run={out['tests_run']} failures={out['failures']} errors={out['errors']} skips={out['skips']} session={out['session']}"
        )
    return 0 if ok else 1


@click.group(help="Unified test runner with parallel sharding")
def test() -> None:  # pragma: no cover - CLI entry
    pass


def _parse_multi(values: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for v in values:
        if not v:
            continue
        parts = [p.strip() for p in v.split(",") if p.strip()]
        items.extend(parts)
    return items


_PHASES: tuple[PhaseName, ...] = ("unit", "js", "integration", "tour")


def _phase_outcomes(focus_phase: PhaseName, outcome: PhaseOutcome) -> dict[str, PhaseOutcome]:
    placeholders = {name: PhaseOutcome(name, None, None, None) for name in _PHASES}
    placeholders[focus_phase] = outcome
    return placeholders


def _run_phase_and_exit(ts: TestSession, phase: PhaseName, timeout: int, json_out: bool) -> None:
    ts.start()
    modules = ts.discover_modules(phase)
    outcome = ts.run_phase(phase, modules, timeout)
    outcomes = _phase_outcomes(phase, outcome)
    rc = ts.finish(outcomes)
    if json_out:
        _emit_bottomline(Path("tmp/test-logs/latest"), True)
    sys.exit(rc)


@test.command("run")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--unit-shards", type=int, default=None, help="Override UNIT_SHARDS")
@click.option("--js-shards", type=int, default=None, help="Override JS_SHARDS")
@click.option("--integration-shards", type=int, default=None, help="Override INTEGRATION_SHARDS")
@click.option("--tour-shards", type=int, default=None, help="Override TOUR_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules (comma or repeat)")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules (comma or repeat)")
# Per-phase filters
@click.option("--unit-modules", multiple=True, help="Unit phase: only include these modules")
@click.option("--unit-exclude", multiple=True, help="Unit phase: exclude these modules")
@click.option("--js-modules", multiple=True, help="JS phase: only include these modules")
@click.option("--js-exclude", multiple=True, help="JS phase: exclude these modules")
@click.option("--integration-modules", multiple=True, help="Integration phase: only include these modules")
@click.option("--integration-exclude", multiple=True, help="Integration phase: exclude these modules")
@click.option("--tour-modules", multiple=True, help="Tour phase: only include these modules")
@click.option("--tour-exclude", multiple=True, help="Tour phase: exclude these modules")
@click.option("--skip-filestore-integration", is_flag=True, help="Skip filestore snapshot in integration phase")
@click.option("--skip-filestore-tour", is_flag=True, help="Skip filestore snapshot in tour phase")
@click.option("--detached", is_flag=True, help="Run in background and return immediately")
@click.option("--unit-within-shards", type=int, default=None, help="Split unit by class across N shards")
@click.option("--integration-within-shards", type=int, default=None, help="Split integration by class across N shards")
@click.option("--tour-within-shards", type=int, default=None, help="Split tour by class across N shards")
@click.option("--overlap", is_flag=True, help="Run phases in parallel (unit+js, integration+tour)")
def run_all(
    json_out: bool,
    unit_shards: int | None,
    js_shards: int | None,
    integration_shards: int | None,
    tour_shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    unit_modules: tuple[str, ...],
    unit_exclude: tuple[str, ...],
    js_modules: tuple[str, ...],
    js_exclude: tuple[str, ...],
    integration_modules: tuple[str, ...],
    integration_exclude: tuple[str, ...],
    tour_modules: tuple[str, ...],
    tour_exclude: tuple[str, ...],
    skip_filestore_integration: bool,
    skip_filestore_tour: bool,
    detached: bool,
    unit_within_shards: int | None,
    integration_within_shards: int | None,
    tour_within_shards: int | None,
    overlap: bool,
) -> None:
    # Set env overrides for settings
    if unit_shards is not None:
        os.environ["UNIT_SHARDS"] = str(unit_shards)
    if js_shards is not None:
        os.environ["JS_SHARDS"] = str(js_shards)
    if integration_shards is not None:
        os.environ["INTEGRATION_SHARDS"] = str(integration_shards)
    if tour_shards is not None:
        os.environ["TOUR_SHARDS"] = str(tour_shards)
    if skip_filestore_integration:
        os.environ["SKIP_FILESTORE_INTEGRATION"] = "1"
    if skip_filestore_tour:
        os.environ["SKIP_FILESTORE_TOUR"] = "1"
    if unit_within_shards is not None:
        os.environ["UNIT_WITHIN_SHARDS"] = str(unit_within_shards)
    if integration_within_shards is not None:
        os.environ["INTEGRATION_WITHIN_SHARDS"] = str(integration_within_shards)
    if tour_within_shards is not None:
        os.environ["TOUR_WITHIN_SHARDS"] = str(tour_within_shards)
    if overlap:
        os.environ["PHASES_OVERLAP"] = "1"
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if detached and not os.environ.get("DETACHED_SPAWNED"):
        # Rebuild command without --detached and spawn
        cmd = ["nohup", "env", "DETACHED_SPAWNED=1", "TEST_DETACHED=1", "uv", "run", "test", "run"]
        if unit_shards is not None:
            cmd += ["--unit-shards", str(unit_shards)]
        if js_shards is not None:
            cmd += ["--js-shards", str(js_shards)]
        if integration_shards is not None:
            cmd += ["--integration-shards", str(integration_shards)]
        if tour_shards is not None:
            cmd += ["--tour-shards", str(tour_shards)]
        for m in include:
            cmd += ["--modules", m]
        for x in omit:
            cmd += ["--exclude", x]
        for m in _parse_multi(unit_modules):
            cmd += ["--unit-modules", m]
        for x in _parse_multi(unit_exclude):
            cmd += ["--unit-exclude", x]
        for m in _parse_multi(js_modules):
            cmd += ["--js-modules", m]
        for x in _parse_multi(js_exclude):
            cmd += ["--js-exclude", x]
        for m in _parse_multi(integration_modules):
            cmd += ["--integration-modules", m]
        for x in _parse_multi(integration_exclude):
            cmd += ["--integration-exclude", x]
        for m in _parse_multi(tour_modules):
            cmd += ["--tour-modules", m]
        for x in _parse_multi(tour_exclude):
            cmd += ["--tour-exclude", x]
        if skip_filestore_integration:
            cmd += ["--skip-filestore-integration"]
        if skip_filestore_tour:
            cmd += ["--skip-filestore-tour"]
        from subprocess import Popen

        out = Path("tmp/test-logs/launcher.out")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("ab", buffering=0) as f:
            Popen(cmd, stdout=f, stderr=f)
        # Try to identify session quickly
        session = None
        cur = Path("tmp/test-logs/current")
        cur_json = cur.with_suffix(".json")
        import time as _t

        for _ in range(30):  # ~3s
            if cur.exists():
                try:
                    session = Path(os.readlink(cur)).name
                except OSError:
                    session = cur.name
                break
            if cur_json.exists():
                data = read_json_file(cur_json)
                if data:
                    session = Path(data.get("current", "")).name or None
                    if session:
                        break
            _t.sleep(0.1)
        payload = {"status": "running", "session": session}
        print(json.dumps(payload))
        sys.exit(0)

    rc = TestSession(
        include_modules=include or None,
        exclude_modules=omit or None,
        unit_modules=_parse_multi(unit_modules) or None,
        unit_exclude=_parse_multi(unit_exclude) or None,
        js_modules=_parse_multi(js_modules) or None,
        js_exclude=_parse_multi(js_exclude) or None,
        integration_modules=_parse_multi(integration_modules) or None,
        integration_exclude=_parse_multi(integration_exclude) or None,
        tour_modules=_parse_multi(tour_modules) or None,
        tour_exclude=_parse_multi(tour_exclude) or None,
    ).run()
    if json_out:
        latest = Path("tmp/test-logs/latest")
        _emit_bottomline(latest, True)
    sys.exit(rc)


@test.command("unit")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override UNIT_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--unit-modules", multiple=True, help="Unit phase: only include these modules")
@click.option("--unit-exclude", multiple=True, help="Unit phase: exclude these modules")
def run_unit(
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    unit_modules: tuple[str, ...],
    unit_exclude: tuple[str, ...],
) -> None:
    if shards is not None:
        os.environ["UNIT_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    ts = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        unit_modules=_parse_multi(unit_modules) or None,
        unit_exclude=_parse_multi(unit_exclude) or None,
    )
    _run_phase_and_exit(ts, "unit", 600, json_out)


@test.command("js")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override JS_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--js-modules", multiple=True, help="JS phase: only include these modules")
@click.option("--js-exclude", multiple=True, help="JS phase: exclude these modules")
@click.option("--detached", is_flag=True, help="Run in background and return immediately")
def run_js(
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    js_modules: tuple[str, ...],
    js_exclude: tuple[str, ...],
    detached: bool,
) -> None:
    if shards is not None:
        os.environ["JS_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if detached and not os.environ.get("DETACHED_SPAWNED"):
        cmd = ["nohup", "env", "DETACHED_SPAWNED=1", "TEST_DETACHED=1", "uv", "run", "test", "js"]
        if shards is not None:
            cmd += ["--shards", str(shards)]
        for m in include:
            cmd += ["--modules", m]
        for x in omit:
            cmd += ["--exclude", x]
        for m in _parse_multi(js_modules):
            cmd += ["--js-modules", m]
        for x in _parse_multi(js_exclude):
            cmd += ["--js-exclude", x]
        from subprocess import Popen

        out = Path("tmp/test-logs/launcher.out")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("ab", buffering=0) as f:
            Popen(cmd, stdout=f, stderr=f)
        print(json.dumps({"status": "running"}))
        sys.exit(0)

    ts = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        js_modules=_parse_multi(js_modules) or None,
        js_exclude=_parse_multi(js_exclude) or None,
    )
    _run_phase_and_exit(ts, "js", 1200, json_out)


@test.command("integration")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override INTEGRATION_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--integration-modules", multiple=True, help="Integration phase: only include these modules")
@click.option("--integration-exclude", multiple=True, help="Integration phase: exclude these modules")
@click.option("--skip-filestore", is_flag=True, help="Skip filestore snapshot for integration")
def run_integration(
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    integration_modules: tuple[str, ...],
    integration_exclude: tuple[str, ...],
    skip_filestore: bool,
) -> None:
    if shards is not None:
        os.environ["INTEGRATION_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if skip_filestore:
        os.environ["SKIP_FILESTORE_INTEGRATION"] = "1"
    ts = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        integration_modules=_parse_multi(integration_modules) or None,
        integration_exclude=_parse_multi(integration_exclude) or None,
    )
    _run_phase_and_exit(ts, "integration", 900, json_out)


@test.command("tour")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override TOUR_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--tour-modules", multiple=True, help="Tour phase: only include these modules")
@click.option("--tour-exclude", multiple=True, help="Tour phase: exclude these modules")
@click.option("--skip-filestore", is_flag=True, help="Skip filestore snapshot for tour")
@click.option("--detached", is_flag=True, help="Run in background and return immediately")
def run_tour(
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    tour_modules: tuple[str, ...],
    tour_exclude: tuple[str, ...],
    skip_filestore: bool,
    detached: bool,
) -> None:
    if shards is not None:
        os.environ["TOUR_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if detached and not os.environ.get("DETACHED_SPAWNED"):
        cmd = ["nohup", "env", "DETACHED_SPAWNED=1", "TEST_DETACHED=1", "uv", "run", "test", "tour"]
        if shards is not None:
            cmd += ["--shards", str(shards)]
        for m in include:
            cmd += ["--modules", m]
        for x in omit:
            cmd += ["--exclude", x]
        for m in _parse_multi(tour_modules):
            cmd += ["--tour-modules", m]
        for x in _parse_multi(tour_exclude):
            cmd += ["--tour-exclude", x]
        if skip_filestore:
            cmd += ["--skip-filestore"]
        from subprocess import DEVNULL, Popen

        Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        print(json.dumps({"status": "running"}))
        sys.exit(0)

    if skip_filestore:
        os.environ["SKIP_FILESTORE_TOUR"] = "1"
    ts = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        tour_modules=_parse_multi(tour_modules) or None,
        tour_exclude=_parse_multi(tour_exclude) or None,
    )
    _run_phase_and_exit(ts, "tour", 1800, json_out)


@test.command("plan")
@click.option("--phase", type=click.Choice(["unit", "js", "integration", "tour", "all"]), default="all")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON plan (default)")
@click.option("--unit-shards", type=int, default=None, help="Override UNIT_SHARDS")
@click.option("--js-shards", type=int, default=None, help="Override JS_SHARDS")
@click.option("--integration-shards", type=int, default=None, help="Override INTEGRATION_SHARDS")
@click.option("--tour-shards", type=int, default=None, help="Override TOUR_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--unit-modules", multiple=True, help="Unit phase: only include these modules")
@click.option("--unit-exclude", multiple=True, help="Unit phase: exclude these modules")
@click.option("--js-modules", multiple=True, help="JS phase: only include these modules")
@click.option("--js-exclude", multiple=True, help="JS phase: exclude these modules")
@click.option("--integration-modules", multiple=True, help="Integration phase: only include these modules")
@click.option("--integration-exclude", multiple=True, help="Integration phase: exclude these modules")
@click.option("--tour-modules", multiple=True, help="Tour phase: only include these modules")
@click.option("--tour-exclude", multiple=True, help="Tour phase: exclude these modules")
def plan_cmd(
    phase: str,
    json_out: bool,
    unit_shards: int | None,
    js_shards: int | None,
    integration_shards: int | None,
    tour_shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    unit_modules: tuple[str, ...],
    unit_exclude: tuple[str, ...],
    js_modules: tuple[str, ...],
    js_exclude: tuple[str, ...],
    integration_modules: tuple[str, ...],
    integration_exclude: tuple[str, ...],
    tour_modules: tuple[str, ...],
    tour_exclude: tuple[str, ...],
) -> None:
    """Print the weight-aware sharding plan for a phase or all phases."""
    # apply overrides to env so TestSession sees them if needed
    if unit_shards is not None:
        os.environ["UNIT_SHARDS"] = str(unit_shards)
    if js_shards is not None:
        os.environ["JS_SHARDS"] = str(js_shards)
    if integration_shards is not None:
        os.environ["INTEGRATION_SHARDS"] = str(integration_shards)
    if tour_shards is not None:
        os.environ["TOUR_SHARDS"] = str(tour_shards)

    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    ts = TestSession(
        include_modules=include or None,
        exclude_modules=omit or None,
        unit_modules=_parse_multi(unit_modules) or None,
        unit_exclude=_parse_multi(unit_exclude) or None,
        js_modules=_parse_multi(js_modules) or None,
        js_exclude=_parse_multi(js_exclude) or None,
        integration_modules=_parse_multi(integration_modules) or None,
        integration_exclude=_parse_multi(integration_exclude) or None,
        tour_modules=_parse_multi(tour_modules) or None,
        tour_exclude=_parse_multi(tour_exclude) or None,
    )

    def _phase_plan(name: PhaseName, shards: int | None) -> dict:
        mods = ts.discover_modules(name)
        if name == "unit":
            n = shards if shards is not None else ts.settings.unit_shards
        elif name == "js":
            n = shards if shards is not None else ts.settings.js_shards
        elif name == "integration":
            n = shards if shards is not None else ts.settings.integration_shards
        else:
            n = shards if shards is not None else ts.settings.tour_shards
        # Resolve auto value if <=0 using session heuristics
        if not mods:
            n_effective = 1
        else:
            if (n or 0) <= 0:
                try:
                    cpu = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
                except (AttributeError, OSError):
                    cpu = os.cpu_count() or 4
                default_auto = 4 if name == "unit" else 2
                n_effective = max(1, min(cpu, default_auto, len(mods)))
            else:
                n_effective = max(1, min(n, len(mods)))  # type: ignore[arg-type]
        plan = plan_shards_for_phase(mods, name, n_effective)
        return {
            "phase": name,
            "shards": plan.shards,
            "total_weight": plan.total_weight,
            "shards_count": plan.shards_count,
            "strategy": plan.strategy,
        }

    phases: list[PhaseName] = list(_PHASES) if phase == "all" else [cast(PhaseName, phase)]
    payload = {"schema": "plan.v1", "phases": {}}
    for ph in phases:
        payload["phases"][ph] = _phase_plan(
            ph,
            unit_shards if ph == "unit" else js_shards if ph == "js" else integration_shards if ph == "integration" else tour_shards,
        )

    output = json.dumps(payload, indent=2)
    if json_out:
        print(output)
    else:
        click.echo(output)
    sys.exit(0)


@test.command("rerun-failures")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def rerun_failures(json_out: bool) -> None:
    """Re-run only failing modules from the latest session.

    Reads per-shard summaries and collects modules for phases that failed; runs a filtered session.
    """
    base = Path("tmp/test-logs/latest")
    if not base.exists():
        print(json.dumps({"status": "no_latest"}) if json_out else "no_latest")
        sys.exit(2)
    phases = {"unit": [], "js": [], "integration": [], "tour": []}
    for ph in phases.keys():
        ph_dir = base / ph
        if not ph_dir.exists():
            continue
        for sf in ph_dir.glob("*.summary.json"):
            data = read_json_file(sf)
            if data is None:
                continue
            rc = int(data.get("returncode") or 0)
            if rc != 0:
                for m in data.get("modules") or []:
                    phases[ph].append(m)
    # Deduplicate
    for k, v in phases.items():
        phases[k] = sorted(set(v))
    payload = {k: v for k, v in phases.items() if v}
    if not payload:
        print(json.dumps({"status": "nothing_to_rerun"}) if json_out else "nothing_to_rerun")
        sys.exit(0)
    if json_out:
        print(json.dumps({"phases": payload}))
    # Build flags
    args: list[str] = ["uv", "run", "test", "run"]
    for m in payload.get("unit", []):
        args += ["--unit-modules", m]
    for m in payload.get("js", []):
        args += ["--js-modules", m]
    for m in payload.get("integration", []):
        args += ["--integration-modules", m]
    for m in payload.get("tour", []):
        args += ["--tour-modules", m]
    from subprocess import call

    sys.exit(call(args))


@test.command("clean")
def run_clean() -> None:
    from .db import cleanup_test_databases
    from .filestore import cleanup_filestores

    # noinspection PyArgumentList
    name = TestSettings().db_name
    click.echo(f"🧹 Cleaning test artifacts for {name}")
    cleanup_test_databases(name)
    cleanup_filestores(name)
    click.echo("✅ Done")


def main() -> None:  # pragma: no cover
    test()


@test.command("status")
@click.option("--session", default=None, help="Specific session dir name (e.g., test-YYYYMMDD_HHMMSS)")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def status_cmd(session: str | None, json_out: bool) -> None:
    base = Path("tmp/test-logs")
    if session:
        latest = base / session
    else:
        cur = base / "current"
        if cur.exists():
            latest = cur
        else:
            latest = base / "latest"
    p = latest / "summary.json"
    if not p.exists():
        out = {"status": "running"}
        print(json.dumps(out) if json_out else "running")
        sys.exit(2)
    data = read_json_file(p)
    if data is None:
        print(json.dumps({"status": "invalid"}) if json_out else "invalid")
        sys.exit(3)
    ok = bool(data.get("success"))
    if json_out:
        print(json.dumps({"success": ok, "summary": str(p.resolve())}))
    else:
        print("success" if ok else "failed")
    sys.exit(0 if ok else 1)


@test.command("wait")
@click.option("--session", default=None, help="Specific session dir name")
@click.option("--timeout", type=int, default=0, help="Max seconds to wait (0 = no limit)")
@click.option("--interval", type=int, default=10, help="Poll interval seconds")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def wait_cmd(session: str | None, timeout: int, interval: int, json_out: bool) -> None:
    import time as _t

    base = Path("tmp/test-logs")
    if session:
        latest = base / session
    else:
        cur = base / "current"
        latest = cur if cur.exists() else base / "latest"
    start = _t.time()
    while True:
        p = latest / "summary.json"
        if p.exists():
            data = read_json_file(p)
            ok = bool((data or {}).get("success"))
            if json_out:
                print(json.dumps({"success": ok, "summary": str(p.resolve())}))
            else:
                print("success" if ok else "failed")
            sys.exit(0 if ok else 1)
        if timeout and (_t.time() - start) > timeout:
            print(json.dumps({"status": "timeout"}) if json_out else "timeout")
            sys.exit(2)
        _t.sleep(max(1, interval))


@test.command("doctor")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def doctor_cmd(json_out: bool) -> None:
    """Quick environment diagnostics for the runner (Docker, DB, disk, shards)."""
    # Docker services
    import subprocess

    services = []
    try:
        res = subprocess.run(["docker", "compose", "ps", "--services"], capture_output=True, text=True)
        if res.returncode == 0:
            services = [s for s in res.stdout.strip().split("\n") if s]
    except OSError:
        services = []
    svc_ok = {}
    for s in ("database", "script-runner"):
        ok = False
        if s in services:
            try:
                r = subprocess.run(["docker", "compose", "exec", "-T", s, "true"], capture_output=True)
                ok = r.returncode == 0
            except OSError:
                ok = False
        svc_ok[s] = ok

    # DB capacity
    try:
        max_conn, active = db_capacity()
    except (OSError, RuntimeError, ValueError):
        max_conn, active = (0, 0)

    # Disk
    try:
        du = disk_usage(".")
        free_pct = round(du.free / du.total * 100, 1)
    except OSError:
        free_pct = -1.0

    # CPU
    cpu = os.cpu_count() or 1

    # Shard guardrails
    # noinspection PyArgumentList
    st = TestSettings()
    allowed = 0
    try:
        allowed = max(1, (max_conn - active - int(st.conn_reserve)) // max(1, int(st.conn_per_shard)))
    except (TypeError, ValueError, ZeroDivisionError):
        allowed = 0

    payload = {
        "docker": {"services": services, "database_ok": svc_ok.get("database"), "script_runner_ok": svc_ok.get("script-runner")},
        "db": {"max_connections": max_conn, "active": active},
        "disk": {"free_percent": free_pct},
        "cpu": {"count": cpu},
        "guardrails": {"conn_per_shard": st.conn_per_shard, "reserve": st.conn_reserve, "suggested_max_shards": allowed},
    }
    if json_out:
        print(json.dumps(payload))
    else:
        click.echo(f"Docker services: {services}")
        click.echo(f"database ok={payload['docker']['database_ok']} script-runner ok={payload['docker']['script_runner_ok']}")
        click.echo(f"DB connections: max={max_conn} active={active} suggested_max_shards={allowed}")
        click.echo(f"Disk free: {free_pct}%")
        click.echo(f"CPUs: {cpu}")
    sys.exit(0)


@test.command("validate")
@click.option("--session", default=None, help="Specific session dir name")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def validate_cmd(session: str | None, json_out: bool) -> None:
    from .validate import validate

    rc = validate(session=session, json_out=json_out)
    raise SystemExit(rc)
