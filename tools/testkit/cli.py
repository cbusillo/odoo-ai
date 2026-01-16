import json
import os
import sys
from pathlib import Path
from shutil import disk_usage

import click

from tools.deployer.settings import discover_repo_root, load_stack_settings

from .db import db_capacity
from .docker_api import compose_env
from .phases import PhaseOutcome
from .reporter import load_json
from .session import PhaseName, TestSession
from .settings import TestSettings
from .sharding import plan_shards_for_phase


def _emit_bottomline(latest: Path, as_json: bool) -> int:
    summary_path = latest / "summary.json"
    if not summary_path.exists():
        if as_json:
            print(json.dumps({"status": "no_summary"}))
        else:
            click.echo("no_summary")
        return 2
    data = load_json(summary_path)
    if data is None:
        if as_json:
            print(json.dumps({"status": "invalid"}))
        else:
            click.echo("invalid")
        return 3
    is_success = bool(data.get("success"))
    total = data.get("counters_total") or {}
    return_codes = data.get("return_codes") or {}
    payload = {
        "success": is_success,
        "tests_run": total.get("tests_run"),
        "failures": total.get("failures"),
        "errors": total.get("errors"),
        "skips": total.get("skips"),
        "return_codes": return_codes,
        "session": data.get("session"),
        "summary": str(summary_path.resolve()),
    }
    if as_json:
        print(json.dumps(payload))
    else:
        click.echo(
            "success={success} tests_run={tests_run} failures={failures} errors={errors} skips={skips} session={session}".format(
                **payload
            )
        )
    return 0 if is_success else 1


@click.group(help="Unified test runner with parallel sharding")
def test() -> None:  # pragma: no cover - CLI entry
    pass


def _parse_multi(values: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for value in values:
        if not value:
            continue
        parts = [part.strip() for part in value.split(",") if part.strip()]
        items.extend(parts)
    return items


def _normalize_stack_name(stack: str | None, env_file: Path | None) -> str | None:
    if stack:
        normalized = stack.strip()
        if not normalized:
            return None
        if normalized.endswith(("-local", "-dev", "-testing", "-prod")):
            return normalized
        return f"{normalized}-local"
    if env_file:
        return env_file.stem
    return None


def _prefer_test_stack(stack: str | None, env_file: Path | None) -> str | None:
    if not stack or env_file:
        return stack
    cleaned = stack.strip()
    if not cleaned:
        return None
    if cleaned.endswith(("-local", "-dev", "-testing", "-prod", "-test")):
        return cleaned
    repo_root = discover_repo_root(Path.cwd())
    candidate = f"{cleaned}-test"
    candidate_env = repo_root / "docker" / "config" / f"{candidate}-local.env"
    if candidate_env.exists():
        return candidate
    return cleaned


def _apply_stack_env(stack: str | None, env_file: str | None) -> None:
    if not stack and not env_file:
        raise click.ClickException(
            "Missing required --stack or --env-file (e.g. --stack opw or --env-file docker/config/opw-local.env)."
        )
    env_path = Path(env_file).expanduser().resolve() if env_file else None
    preferred_stack = _prefer_test_stack(stack, env_path)
    stack_name = _normalize_stack_name(preferred_stack, env_path)
    if stack_name is None:
        raise click.ClickException("Unable to resolve stack name; provide --stack or --env-file.")
    settings = load_stack_settings(stack_name, env_path)
    os.environ.update(settings.environment)
    os.environ["TESTKIT_ENV_FILE"] = str(settings.env_file)
    os.environ["ODOO_STACK_NAME"] = stack_name
    os.environ["TESTKIT_DISABLE_DEV_MODE"] = "1"


def _apply_shard_overrides(
    unit_shards: int | None,
    js_shards: int | None,
    integration_shards: int | None,
    tour_shards: int | None,
) -> None:
    if unit_shards is not None:
        os.environ["UNIT_SHARDS"] = str(unit_shards)
    if js_shards is not None:
        os.environ["JS_SHARDS"] = str(js_shards)
    if integration_shards is not None:
        os.environ["INTEGRATION_SHARDS"] = str(integration_shards)
    if tour_shards is not None:
        os.environ["TOUR_SHARDS"] = str(tour_shards)


def _build_session(
    *,
    include: list[str],
    omit: list[str],
    unit_modules: tuple[str, ...],
    unit_exclude: tuple[str, ...],
    js_modules: tuple[str, ...],
    js_exclude: tuple[str, ...],
    integration_modules: tuple[str, ...],
    integration_exclude: tuple[str, ...],
    tour_modules: tuple[str, ...],
    tour_exclude: tuple[str, ...],
    keep_going: bool | None = None,
) -> TestSession:
    return TestSession(
        keep_going=keep_going,
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


_PHASES: tuple[PhaseName, ...] = ("unit", "js", "integration", "tour")


def _phase_outcomes(focus_phase: PhaseName, outcome: PhaseOutcome) -> dict[str, PhaseOutcome]:
    placeholders = {name: PhaseOutcome(name, None, None, None) for name in _PHASES}
    placeholders[focus_phase] = outcome
    return placeholders


def _run_phase_and_exit(test_session: TestSession, phase: PhaseName, timeout: int, json_out: bool) -> None:
    test_session.start()
    modules = test_session.discover_modules(phase)
    outcome = test_session.run_phase(phase, modules, timeout)
    outcomes = _phase_outcomes(phase, outcome)
    return_code = test_session.finish(outcomes)
    if json_out:
        _emit_bottomline(Path("tmp/test-logs/latest"), True)
    sys.exit(return_code)


@test.command("run")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
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
    stack: str | None,
    env_file: str | None,
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
    _apply_stack_env(stack, env_file)
    # Set env overrides for settings
    _apply_shard_overrides(unit_shards, js_shards, integration_shards, tour_shards)
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
        detached_command = [
            "nohup",
            "env",
            "DETACHED_SPAWNED=1",
            "TEST_DETACHED=1",
            "uv",
            "run",
            "test",
            "run",
        ]
        if unit_shards is not None:
            detached_command += ["--unit-shards", str(unit_shards)]
        if js_shards is not None:
            detached_command += ["--js-shards", str(js_shards)]
        if integration_shards is not None:
            detached_command += ["--integration-shards", str(integration_shards)]
        if tour_shards is not None:
            detached_command += ["--tour-shards", str(tour_shards)]
        for module_name in include:
            detached_command += ["--modules", module_name]
        for excluded_module in omit:
            detached_command += ["--exclude", excluded_module]
        for module_name in _parse_multi(unit_modules):
            detached_command += ["--unit-modules", module_name]
        for excluded_module in _parse_multi(unit_exclude):
            detached_command += ["--unit-exclude", excluded_module]
        for module_name in _parse_multi(js_modules):
            detached_command += ["--js-modules", module_name]
        for excluded_module in _parse_multi(js_exclude):
            detached_command += ["--js-exclude", excluded_module]
        for module_name in _parse_multi(integration_modules):
            detached_command += ["--integration-modules", module_name]
        for excluded_module in _parse_multi(integration_exclude):
            detached_command += ["--integration-exclude", excluded_module]
        for module_name in _parse_multi(tour_modules):
            detached_command += ["--tour-modules", module_name]
        for excluded_module in _parse_multi(tour_exclude):
            detached_command += ["--tour-exclude", excluded_module]
        if stack:
            detached_command += ["--stack", stack]
        if env_file:
            detached_command += ["--env-file", env_file]
        if skip_filestore_integration:
            detached_command += ["--skip-filestore-integration"]
        if skip_filestore_tour:
            detached_command += ["--skip-filestore-tour"]
        from subprocess import Popen

        launcher_log = Path("tmp/test-logs/launcher.out")
        launcher_log.parent.mkdir(parents=True, exist_ok=True)
        with launcher_log.open("ab", buffering=0) as log_handle:
            Popen(detached_command, stdout=log_handle, stderr=log_handle)
        # Try to identify session quickly
        session = None
        current_pointer = Path("tmp/test-logs/current")
        current_json = current_pointer.with_suffix(".json")
        import time as time_module

        for _ in range(30):  # ~3s
            if current_pointer.exists():
                try:
                    session = Path(os.readlink(current_pointer)).name
                except OSError:
                    session = current_pointer.name
                break
            if current_json.exists():
                data = load_json(current_json)
                if data:
                    session = Path(data.get("current", "")).name or None
                    if session:
                        break
            time_module.sleep(0.1)
        payload = {"status": "running", "session": session}
        print(json.dumps(payload))
        sys.exit(0)

    return_code = _build_session(
        include=include,
        omit=omit,
        unit_modules=unit_modules,
        unit_exclude=unit_exclude,
        js_modules=js_modules,
        js_exclude=js_exclude,
        integration_modules=integration_modules,
        integration_exclude=integration_exclude,
        tour_modules=tour_modules,
        tour_exclude=tour_exclude,
    ).run()
    if json_out:
        latest = Path("tmp/test-logs/latest")
        _emit_bottomline(latest, True)
    sys.exit(return_code)


@test.command("unit")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override UNIT_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--unit-modules", multiple=True, help="Unit phase: only include these modules")
@click.option("--unit-exclude", multiple=True, help="Unit phase: exclude these modules")
def run_unit(
    stack: str | None,
    env_file: str | None,
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    unit_modules: tuple[str, ...],
    unit_exclude: tuple[str, ...],
) -> None:
    _apply_stack_env(stack, env_file)
    if shards is not None:
        os.environ["UNIT_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    test_session = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        unit_modules=_parse_multi(unit_modules) or None,
        unit_exclude=_parse_multi(unit_exclude) or None,
    )
    _run_phase_and_exit(test_session, "unit", 600, json_out)


@test.command("js")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override JS_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--js-modules", multiple=True, help="JS phase: only include these modules")
@click.option("--js-exclude", multiple=True, help="JS phase: exclude these modules")
@click.option("--detached", is_flag=True, help="Run in background and return immediately")
def run_js(
    stack: str | None,
    env_file: str | None,
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    js_modules: tuple[str, ...],
    js_exclude: tuple[str, ...],
    detached: bool,
) -> None:
    _apply_stack_env(stack, env_file)
    if shards is not None:
        os.environ["JS_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if detached and not os.environ.get("DETACHED_SPAWNED"):
        detached_command = [
            "nohup",
            "env",
            "DETACHED_SPAWNED=1",
            "TEST_DETACHED=1",
            "uv",
            "run",
            "test",
            "js",
        ]
        if shards is not None:
            detached_command += ["--shards", str(shards)]
        for module_name in include:
            detached_command += ["--modules", module_name]
        for excluded_module in omit:
            detached_command += ["--exclude", excluded_module]
        for module_name in _parse_multi(js_modules):
            detached_command += ["--js-modules", module_name]
        for excluded_module in _parse_multi(js_exclude):
            detached_command += ["--js-exclude", excluded_module]
        if stack:
            detached_command += ["--stack", stack]
        if env_file:
            detached_command += ["--env-file", env_file]
        from subprocess import Popen

        launcher_log = Path("tmp/test-logs/launcher.out")
        launcher_log.parent.mkdir(parents=True, exist_ok=True)
        with launcher_log.open("ab", buffering=0) as log_handle:
            Popen(detached_command, stdout=log_handle, stderr=log_handle)
        print(json.dumps({"status": "running"}))
        sys.exit(0)

    test_session = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        js_modules=_parse_multi(js_modules) or None,
        js_exclude=_parse_multi(js_exclude) or None,
    )
    _run_phase_and_exit(test_session, "js", 1200, json_out)


@test.command("integration")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override INTEGRATION_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--integration-modules", multiple=True, help="Integration phase: only include these modules")
@click.option("--integration-exclude", multiple=True, help="Integration phase: exclude these modules")
@click.option("--skip-filestore", is_flag=True, help="Skip filestore snapshot for integration")
def run_integration(
    stack: str | None,
    env_file: str | None,
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    integration_modules: tuple[str, ...],
    integration_exclude: tuple[str, ...],
    skip_filestore: bool,
) -> None:
    _apply_stack_env(stack, env_file)
    if shards is not None:
        os.environ["INTEGRATION_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if skip_filestore:
        os.environ["SKIP_FILESTORE_INTEGRATION"] = "1"
    test_session = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        integration_modules=_parse_multi(integration_modules) or None,
        integration_exclude=_parse_multi(integration_exclude) or None,
    )
    _run_phase_and_exit(test_session, "integration", 900, json_out)


@test.command("tour")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Print bottom-line JSON at end")
@click.option("--shards", type=int, default=None, help="Override TOUR_SHARDS")
@click.option("--modules", "modules", multiple=True, help="Only include these modules")
@click.option("--exclude", "exclude", multiple=True, help="Exclude these modules")
@click.option("--tour-modules", multiple=True, help="Tour phase: only include these modules")
@click.option("--tour-exclude", multiple=True, help="Tour phase: exclude these modules")
@click.option("--skip-filestore", is_flag=True, help="Skip filestore snapshot for tour")
@click.option("--detached", is_flag=True, help="Run in background and return immediately")
def run_tour(
    stack: str | None,
    env_file: str | None,
    json_out: bool,
    shards: int | None,
    modules: tuple[str, ...],
    exclude: tuple[str, ...],
    tour_modules: tuple[str, ...],
    tour_exclude: tuple[str, ...],
    skip_filestore: bool,
    detached: bool,
) -> None:
    _apply_stack_env(stack, env_file)
    if shards is not None:
        os.environ["TOUR_SHARDS"] = str(shards)
    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    if detached and not os.environ.get("DETACHED_SPAWNED"):
        detached_command = [
            "nohup",
            "env",
            "DETACHED_SPAWNED=1",
            "TEST_DETACHED=1",
            "uv",
            "run",
            "test",
            "tour",
        ]
        if shards is not None:
            detached_command += ["--shards", str(shards)]
        for module_name in include:
            detached_command += ["--modules", module_name]
        for excluded_module in omit:
            detached_command += ["--exclude", excluded_module]
        for module_name in _parse_multi(tour_modules):
            detached_command += ["--tour-modules", module_name]
        for excluded_module in _parse_multi(tour_exclude):
            detached_command += ["--tour-exclude", excluded_module]
        if skip_filestore:
            detached_command += ["--skip-filestore"]
        if stack:
            detached_command += ["--stack", stack]
        if env_file:
            detached_command += ["--env-file", env_file]
        from subprocess import DEVNULL, Popen

        Popen(detached_command, stdout=DEVNULL, stderr=DEVNULL)
        print(json.dumps({"status": "running"}))
        sys.exit(0)

    if skip_filestore:
        os.environ["SKIP_FILESTORE_TOUR"] = "1"
    test_session = TestSession(
        keep_going=True,
        include_modules=include or None,
        exclude_modules=omit or None,
        tour_modules=_parse_multi(tour_modules) or None,
        tour_exclude=_parse_multi(tour_exclude) or None,
    )
    _run_phase_and_exit(test_session, "tour", 1800, json_out)


@test.command("plan")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
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
    stack: str | None,
    env_file: str | None,
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
    _apply_stack_env(stack, env_file)
    # apply overrides to env so TestSession sees them if needed
    _apply_shard_overrides(unit_shards, js_shards, integration_shards, tour_shards)

    include = _parse_multi(modules)
    omit = _parse_multi(exclude)
    test_session = _build_session(
        include=include,
        omit=omit,
        unit_modules=unit_modules,
        unit_exclude=unit_exclude,
        js_modules=js_modules,
        js_exclude=js_exclude,
        integration_modules=integration_modules,
        integration_exclude=integration_exclude,
        tour_modules=tour_modules,
        tour_exclude=tour_exclude,
    )

    def _phase_plan(name: PhaseName, shards: int | None) -> dict:
        module_names = test_session.discover_modules(name)
        if name == "unit":
            shard_count = shards if shards is not None else test_session.settings.unit_shards
        elif name == "js":
            shard_count = shards if shards is not None else test_session.settings.js_shards
        elif name == "integration":
            shard_count = shards if shards is not None else test_session.settings.integration_shards
        else:
            shard_count = shards if shards is not None else test_session.settings.tour_shards
        # Resolve auto value if <=0 using session heuristics
        if not module_names:
            effective_shards = 1
        else:
            if (shard_count or 0) <= 0:
                try:
                    cpu_count = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
                except (AttributeError, OSError):
                    cpu_count = os.cpu_count() or 4
                default_auto = 4 if name == "unit" else 2
                effective_shards = max(1, min(cpu_count, default_auto, len(module_names)))
            else:
                effective_shards = max(1, min(shard_count, len(module_names)))  # type: ignore[arg-type]
        plan = plan_shards_for_phase(module_names, name, effective_shards)
        return {
            "phase": name,
            "shards": plan.shards,
            "total_weight": plan.total_weight,
            "shards_count": plan.shards_count,
            "strategy": plan.strategy,
        }

    if phase == "all":
        phases = list(_PHASES)
    else:
        phase_name = next(value for value in _PHASES if value == phase)
        phases = [phase_name]
    payload = {"schema": "plan.v1", "phases": {}}
    for phase_name in phases:
        if phase_name == "unit":
            phase_shards = unit_shards
        elif phase_name == "js":
            phase_shards = js_shards
        elif phase_name == "integration":
            phase_shards = integration_shards
        else:
            phase_shards = tour_shards
        payload["phases"][phase_name] = _phase_plan(phase_name, phase_shards)

    output = json.dumps(payload, indent=2)
    if json_out:
        print(output)
    else:
        click.echo(output)
    sys.exit(0)


@test.command("rerun-failures")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def rerun_failures(stack: str | None, env_file: str | None, json_out: bool) -> None:
    """Re-run only failing modules from the latest session.

    Reads per-shard summaries and collects modules for phases that failed; runs a filtered session.
    """
    _apply_stack_env(stack, env_file)
    base = Path("tmp/test-logs/latest")
    if not base.exists():
        print(json.dumps({"status": "no_latest"}) if json_out else "no_latest")
        sys.exit(2)
    phases = {"unit": [], "js": [], "integration": [], "tour": []}
    for phase_name in phases.keys():
        phase_dir = base / phase_name
        if not phase_dir.exists():
            continue
        for summary_file in phase_dir.glob("*.summary.json"):
            data = load_json(summary_file)
            if data is None:
                continue
            return_code = int(data.get("returncode") or 0)
            if return_code != 0:
                for module_name in data.get("modules") or []:
                    phases[phase_name].append(module_name)
    # Deduplicate
    for phase_name, module_names in phases.items():
        phases[phase_name] = sorted(set(module_names))
    payload = {phase_name: module_names for phase_name, module_names in phases.items() if module_names}
    if not payload:
        print(json.dumps({"status": "nothing_to_rerun"}) if json_out else "nothing_to_rerun")
        sys.exit(0)
    if json_out:
        print(json.dumps({"phases": payload}))
    # Build flags
    args: list[str] = ["uv", "run", "test", "run"]
    for module_name in payload.get("unit", []):
        args += ["--unit-modules", module_name]
    for module_name in payload.get("js", []):
        args += ["--js-modules", module_name]
    for module_name in payload.get("integration", []):
        args += ["--integration-modules", module_name]
    for module_name in payload.get("tour", []):
        args += ["--tour-modules", module_name]
    if stack:
        args += ["--stack", stack]
    if env_file:
        args += ["--env-file", env_file]
    from subprocess import call

    sys.exit(call(args))


@test.command("clean")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
def run_clean(stack: str | None, env_file: str | None) -> None:
    _apply_stack_env(stack, env_file)
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
    base_dir = Path("tmp/test-logs")
    if session:
        latest = base_dir / session
    else:
        current_pointer = base_dir / "current"
        if current_pointer.exists():
            latest = current_pointer
        else:
            latest = base_dir / "latest"
    summary_path = latest / "summary.json"
    if not summary_path.exists():
        payload = {"status": "running"}
        print(json.dumps(payload) if json_out else "running")
        sys.exit(2)
    data = load_json(summary_path)
    if data is None:
        print(json.dumps({"status": "invalid"}) if json_out else "invalid")
        sys.exit(3)
    is_success = bool(data.get("success"))
    if json_out:
        print(json.dumps({"success": is_success, "summary": str(summary_path.resolve())}))
    else:
        print("success" if is_success else "failed")
    sys.exit(0 if is_success else 1)


@test.command("wait")
@click.option("--session", default=None, help="Specific session dir name")
@click.option("--timeout", type=int, default=0, help="Max seconds to wait (0 = no limit)")
@click.option("--interval", type=int, default=10, help="Poll interval seconds")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def wait_cmd(session: str | None, timeout: int, interval: int, json_out: bool) -> None:
    import time as time_module

    base_dir = Path("tmp/test-logs")
    if session:
        latest = base_dir / session
    else:
        current_pointer = base_dir / "current"
        latest = current_pointer if current_pointer.exists() else base_dir / "latest"
    start_time = time_module.time()
    while True:
        summary_path = latest / "summary.json"
        if summary_path.exists():
            data = load_json(summary_path)
            is_success = bool((data or {}).get("success"))
            if json_out:
                print(json.dumps({"success": is_success, "summary": str(summary_path.resolve())}))
            else:
                print("success" if is_success else "failed")
            sys.exit(0 if is_success else 1)
        if timeout and (time_module.time() - start_time) > timeout:
            print(json.dumps({"status": "timeout"}) if json_out else "timeout")
            sys.exit(2)
        time_module.sleep(max(1, interval))


@test.command("doctor")
@click.option("--stack", default=None, help="Use local stack env (e.g. opw, cm, opw-local)")
@click.option("--env-file", "env_file", default=None, help="Explicit env file for stack resolution")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def doctor_cmd(stack: str | None, env_file: str | None, json_out: bool) -> None:
    """Quick environment diagnostics for the runner (Docker, DB, disk, shards)."""
    _apply_stack_env(stack, env_file)
    # Docker services
    import subprocess

    services: list[str] = []
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--services"],
            capture_output=True,
            text=True,
            env=compose_env(),
        )
        if result.returncode == 0:
            services = [service_name for service_name in result.stdout.strip().split("\n") if service_name]
    except OSError:
        services = []
    service_statuses: dict[str, bool] = {}
    for service_name in ("database", "script-runner"):
        is_service_ok = False
        if service_name in services:
            try:
                command_result = subprocess.run(
                    ["docker", "compose", "exec", "-T", service_name, "true"],
                    capture_output=True,
                    env=compose_env(),
                )
                is_service_ok = command_result.returncode == 0
            except OSError:
                is_service_ok = False
        service_statuses[service_name] = is_service_ok

    # DB capacity
    try:
        max_conn, active = db_capacity()
    except (OSError, RuntimeError, ValueError):
        max_conn, active = (0, 0)

    # Disk
    try:
        disk_usage_info = disk_usage(".")
        free_pct = round(disk_usage_info.free / disk_usage_info.total * 100, 1)
    except OSError:
        free_pct = -1.0

    # CPU
    cpu_count = os.cpu_count() or 1

    # Shard guardrails
    # noinspection PyArgumentList
    settings = TestSettings()
    try:
        suggested_max_shards = max(
            1,
            (max_conn - active - int(settings.conn_reserve)) // max(1, int(settings.conn_per_shard)),
        )
    except (TypeError, ValueError, ZeroDivisionError):
        suggested_max_shards = 0

    payload = {
        "docker": {
            "services": services,
            "database_ok": service_statuses.get("database"),
            "script_runner_ok": service_statuses.get("script-runner"),
        },
        "db": {"max_connections": max_conn, "active": active},
        "disk": {"free_percent": free_pct},
        "cpu": {"count": cpu_count},
        "guardrails": {
            "conn_per_shard": settings.conn_per_shard,
            "reserve": settings.conn_reserve,
            "suggested_max_shards": suggested_max_shards,
        },
    }
    if json_out:
        print(json.dumps(payload))
    else:
        click.echo(f"Docker services: {services}")
        click.echo(f"database ok={payload['docker']['database_ok']} script-runner ok={payload['docker']['script_runner_ok']}")
        click.echo(f"DB connections: max={max_conn} active={active} suggested_max_shards={suggested_max_shards}")
        click.echo(f"Disk free: {free_pct}%")
        click.echo(f"CPUs: {cpu_count}")
    sys.exit(0)


@test.command("validate")
@click.option("--session", default=None, help="Specific session dir name")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def validate_cmd(session: str | None, json_out: bool) -> None:
    from .validate import validate

    return_code = validate(session=session, json_out=json_out)
    raise SystemExit(return_code)
