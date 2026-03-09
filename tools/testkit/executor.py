import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .auth import setup_test_authentication
from .browser import kill_browsers_and_zombies, restart_script_runner_with_orphan_cleanup
from .counts import count_js_tests, count_py_tests
from .coverage import CoverageRun, build_coverage_run
from .db import (
    clone_production_database,
    contains_default_database_target,
    drop_and_create,
    drop_and_create_test_database,
    get_production_db_name,
    resolve_database_connection_flags,
    split_modules_for_install,
)
from .docker_api import _is_truthy, compose_env, get_script_runner_service
from .events import EventStream
from .filestore import cleanup_single_test_filestore, filestore_exists, snapshot_filestore
from .reporter import write_junit_for_shard
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings

_logger = logging.getLogger(__name__)
_UNITTEST_HEADER_RE = re.compile(r"^(FAIL|ERROR): .+\(.+\)$")
_ODOO_TEST_RESULT_RE = re.compile(r"of (\d+) tests")
_ODOO_TEST_RESULT_COUNTS_RE = re.compile(r"(\d+) failed, (\d+) error\(s\) of (\d+) tests")
_ODOO_TEST_STATS_RE = re.compile(r"odoo\.tests\.stats: .*?: (\d+) tests")
_TESTKIT_PYTHONPATH = "/opt/project/tools/testkit"
_SENSITIVE_ARGUMENT_NAMES = frozenset(
    {
        "PASSWORD",
        "MASTER_PASSWORD",
        "DB_PASSWORD",
        "ODOO_DB_PASSWORD",
        "ODOO_TEST_PASSWORD",
        "ODOO_MASTER_PASSWORD",
        "TOKEN",
        "SECRET",
        "ODOO_KEY",
    }
)
_SENSITIVE_ARGUMENT_SUFFIXES = ("_PASSWORD", "_TOKEN", "_SECRET", "_KEY")
_SENSITIVE_SPLIT_FLAGS = frozenset({"--password", "--master-password", "--db_password"})


def _normalize(line: str) -> str:
    line = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", "[TIMESTAMP]", line)
    line = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[IP]", line)
    line = re.sub(r"\b\d+\b", "[NUM]", line)
    line = re.sub(r"\d+\.\d+(?:-\d+)?", "[VERSION]", line)
    return " ".join(line.split()).strip()


def _detect_repetitive(recent_lines: list[str], seen: dict[str, int], min_occ: int = 5) -> tuple[bool, str]:
    if len(recent_lines) < min_occ:
        return False, ""
    for recent_line in recent_lines:
        normalized_line = _normalize(recent_line)
        if normalized_line and len(normalized_line) > 20:
            seen[normalized_line] = seen.get(normalized_line, 0) + 1
    if not seen:
        return False, ""
    pattern, count = max(seen.items(), key=lambda item: item[1])
    recent_normalized = [_normalize(recent_line) for recent_line in recent_lines]
    ratio = sum(1 for normalized_line in recent_normalized if normalized_line == pattern) / len(recent_normalized)
    if count >= min_occ and ratio > 0.7:
        sample = next((recent_line for recent_line in recent_lines if _normalize(recent_line) == pattern), "")
        sample = sample[:100] + "..." if len(sample) > 100 else sample
        return True, f"Repetitive pattern detected ({count} times, {ratio:.1%}): {sample}"
    return False, ""


def _match_unittest_header(line: str) -> str | None:
    match = _UNITTEST_HEADER_RE.match(line)
    if not match:
        return None
    return match.group(1).lower()


def _prepend_pythonpath(existing: str | None, extra: str) -> str:
    if not existing:
        return extra
    parts = [part for part in existing.split(":") if part]
    if extra in parts:
        return existing
    return f"{extra}:{existing}"


def _sanitize_container_name(value: str) -> str:
    lowered = value.lower()
    sanitized = re.sub(r"[^a-z0-9_.-]+", "-", lowered)
    return sanitized.strip("-") or "testkit-shard"


def _normalize_secret_key(raw_key: str) -> str:
    return raw_key.strip().lstrip("-").replace("-", "_").upper()


def _is_sensitive_key(raw_key: str) -> bool:
    normalized_key = _normalize_secret_key(raw_key)
    if normalized_key in _SENSITIVE_ARGUMENT_NAMES:
        return True
    return any(normalized_key.endswith(suffix) for suffix in _SENSITIVE_ARGUMENT_SUFFIXES)


def _redact_assignment_token(token: str) -> str:
    if "=" not in token:
        return token
    key, _, _value = token.partition("=")
    if _is_sensitive_key(key):
        return f"{key}=***"
    return token


def _redact_command_for_logging(command: list[str]) -> list[str]:
    redacted_command: list[str] = []
    index = 0
    while index < len(command):
        command_part = command[index]
        if command_part == "-e" and index + 1 < len(command):
            redacted_command.extend([command_part, _redact_assignment_token(command[index + 1])])
            index += 2
            continue

        redacted_command.append(_redact_assignment_token(command_part))
        if command_part in _SENSITIVE_SPLIT_FLAGS and index + 1 < len(command):
            redacted_command.append("***")
            index += 2
            continue

        index += 1
    return redacted_command


def _sanitize_database_flags_for_summary(database_flags: list[str]) -> list[str]:
    return [_redact_assignment_token(database_flag) for database_flag in database_flags]


@dataclass
class ExecResult:
    returncode: int
    log_file: Path
    summary_file: Path


OutcomeKind = Literal["success", "test_failure", "infra_failure", "harness_failure"]


@dataclass(frozen=True)
class ShardExecutionRequest:
    test_tags: str
    db_name: str
    modules_to_install: tuple[str, ...]
    timeout: int
    is_tour_test: bool = False
    is_js_test: bool = False
    use_production_clone: bool = False
    template_db: str | None = None
    use_module_prefix: bool = False
    extra_env: dict[str, str] | None = None
    shard_label: str | None = None


@dataclass
class PreparedShardExecution:
    command: list[str]
    compose_environment: dict[str, str]
    database_flags: list[str]
    sanitized_database_flags: list[str]
    memory_limit_flags: list[str]
    redacted_command: list[str]
    phase_dir: Path
    log_file: Path
    summary_file: Path
    container_name: str
    db_name: str
    test_tags: str
    modules_to_install: list[str]
    worker_count: int
    development_mode: str
    timeout: int
    test_type: str


@dataclass
class ShardRuntimeResult:
    returncode: int
    counters: dict[str, int]
    stats_tests_total: int = 0
    result_tests_total: int | None = None
    timed_out: bool = False
    default_database_target: bool = False
    repetitive_pattern: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ShardOutcome:
    outcome_kind: OutcomeKind
    failure_reasons: tuple[str, ...]
    success: bool
    returncode: int
    expected_tests: int
    missing_tests: int


def _resolve_test_tags(
    settings: TestSettings,
    request: ShardExecutionRequest,
) -> tuple[str, bool]:
    use_module_prefix = request.use_module_prefix
    test_tags_override = (settings.test_tags_override or "").strip()
    if test_tags_override:
        if request.is_tour_test:
            must = "tour_test"
        elif request.is_js_test:
            must = "js_test"
        elif request.test_tags and "integration" in request.test_tags:
            must = "integration_test"
        else:
            must = "unit_test"
        tag_parts: list[str] = []
        if must and must not in test_tags_override:
            tag_parts.append(must)
        tag_parts.append(test_tags_override)
        test_tags_final = ",".join(tag_part for tag_part in tag_parts if tag_part)
        use_module_prefix = False
        print(f"[override] Using TEST_TAGS override: {test_tags_final}")
        return test_tags_final, use_module_prefix

    if not request.test_tags:
        return ",".join([f"/{module_name}" for module_name in request.modules_to_install]), use_module_prefix
    if not use_module_prefix:
        return request.test_tags, use_module_prefix

    tag_parts = [tag_part.strip() for tag_part in request.test_tags.split(",") if tag_part.strip()]
    if len(tag_parts) == 1 and not tag_parts[0].startswith("-"):
        tag = tag_parts[0]
        return ",".join([f"{tag}/{module_name}" for module_name in request.modules_to_install]), use_module_prefix

    primary_tag = next(
        (tag_part for tag_part in reversed(tag_parts) if not tag_part.startswith("-")),
        tag_parts[-1],
    )
    scoped_tags = [f"{primary_tag}/{module_name}" for module_name in request.modules_to_install]
    kept_tags = [tag_part for tag_part in tag_parts if tag_part != primary_tag]
    return ",".join(kept_tags + scoped_tags), use_module_prefix


def _prepare_database_state(
    settings: TestSettings,
    request: ShardExecutionRequest,
    *,
    test_tags_final: str,
) -> tuple[list[str], list[str]]:
    restart_script_runner_with_orphan_cleanup()
    if request.is_js_test or request.is_tour_test:
        kill_browsers_and_zombies()
    if request.template_db:
        drop_and_create(request.db_name, request.template_db)
    elif request.use_production_clone:
        clone_production_database(request.db_name)
    else:
        drop_and_create_test_database(request.db_name)

    if request.use_production_clone:
        need_filestore = request.is_tour_test or ("tour" in test_tags_final) or ("integration" in test_tags_final)
        if need_filestore:
            skip_filestore = settings.skip_filestore_tour if request.is_tour_test else settings.skip_filestore_integration
            if not skip_filestore and not filestore_exists(request.db_name):
                snapshot_filestore(request.db_name, get_production_db_name())
            kill_browsers_and_zombies()
    else:
        try:
            cleanup_single_test_filestore(request.db_name)
        except OSError as exc:
            _logger.debug("executor: failed to cleanup filestore %s (%s)", request.db_name, exc)
        if request.is_js_test or request.is_tour_test:
            setup_test_authentication(request.db_name)

    install_modules = list(request.modules_to_install)
    update_modules: list[str] = []
    if request.use_production_clone or request.template_db:
        install_modules, update_modules = split_modules_for_install(request.db_name, list(request.modules_to_install))
    if request.template_db and not request.use_production_clone and not update_modules and install_modules:
        update_modules = install_modules
        install_modules = []
    return install_modules, update_modules


def _shard_base(module_names: list[str], *, use_module_prefix: bool, shard_label: str | None) -> str:
    if use_module_prefix and len(module_names) == 1:
        shard_base = module_names[0]
    else:
        module_key = ",".join(sorted(module_names))
        hash_prefix = hashlib.sha1(module_key.encode()).hexdigest()[:8]
        shard_base = f"shard-{hash_prefix}"
    if shard_label:
        shard_base = f"{shard_base}-{shard_label}"
    return shard_base


def _resolve_limit_memory_flags(resolved_compose_environment: dict[str, str]) -> list[str]:
    limit_memory_flags: list[str] = []
    for environment_key, cli_option in (
        ("ODOO_LIMIT_MEMORY_SOFT", "--limit-memory-soft"),
        ("ODOO_LIMIT_MEMORY_HARD", "--limit-memory-hard"),
    ):
        configured_value = (
            os.environ.get(environment_key)
            or resolved_compose_environment.get(environment_key)
            or ""
        ).strip()
        if configured_value:
            limit_memory_flags.append(f"{cli_option}={configured_value}")
    return limit_memory_flags


def _resolve_worker_settings(
    settings: TestSettings,
    request: ShardExecutionRequest,
    *,
    skip_autoreload: bool,
) -> tuple[int, str]:
    development_mode = "none" if skip_autoreload else "assets"
    if request.is_tour_test or request.is_js_test:
        tour_workers_default = int(settings.tour_workers)
        js_workers_default = int(settings.js_workers)
        worker_count = js_workers_default if request.is_js_test else tour_workers_default
        return worker_count, development_mode
    return 0, development_mode


def _count_expected_tests(category: str, module_names: list[str]) -> int:
    expected_tests = 0
    if category not in {"unit", "integration", "tour", "js"}:
        return 0
    for module_name in module_names:
        module_root = Path("addons") / module_name
        if not module_root.exists():
            continue
        if category == "unit":
            expected_tests += count_py_tests(module_root.glob("**/tests/unit/**/*.py"))
        elif category == "integration":
            expected_tests += count_py_tests(module_root.glob("**/tests/integration/**/*.py"))
        elif category == "tour":
            expected_tests += count_py_tests(module_root.glob("**/tests/tour/**/*.py"))
        elif category == "js":
            expected_tests += count_js_tests(module_root.glob("static/tests/**/*.test.js"))
    return expected_tests


def _classify_outcome(
    runtime: ShardRuntimeResult,
    *,
    expected_tests: int,
) -> ShardOutcome:
    tests_run = int(runtime.counters.get("tests_run", 0) or 0)
    failure_count = int(runtime.counters.get("failures", 0) or 0)
    error_count = int(runtime.counters.get("errors", 0) or 0)
    missing_tests = expected_tests if expected_tests and tests_run == 0 else 0

    harness_reasons: list[str] = []
    infra_reasons: list[str] = []
    test_reasons: list[str] = []

    if runtime.default_database_target:
        harness_reasons.append("default_database_target")
    if missing_tests:
        harness_reasons.append("missing_expected_tests")
    if runtime.error:
        infra_reasons.append("process_error")
    if runtime.timed_out:
        infra_reasons.append("timed_out")
    if failure_count or error_count:
        test_reasons.append("reported_test_failures")
    elif runtime.returncode != 0 and tests_run > 0:
        test_reasons.append("nonzero_exit_with_tests")
    elif runtime.returncode != 0:
        infra_reasons.append("nonzero_exit_without_test_counters")

    if harness_reasons:
        outcome_kind: OutcomeKind = "harness_failure"
        failure_reasons = tuple(harness_reasons + test_reasons + infra_reasons)
    elif test_reasons:
        outcome_kind = "test_failure"
        failure_reasons = tuple(test_reasons + infra_reasons)
    elif infra_reasons:
        outcome_kind = "infra_failure"
        failure_reasons = tuple(infra_reasons)
    else:
        outcome_kind = "success"
        failure_reasons = ()

    return_code = int(runtime.returncode)
    if outcome_kind != "success" and return_code == 0:
        return_code = 1

    return ShardOutcome(
        outcome_kind=outcome_kind,
        failure_reasons=failure_reasons,
        success=outcome_kind == "success",
        returncode=return_code,
        expected_tests=expected_tests,
        missing_tests=missing_tests,
    )


def _run_prepared_execution(
    prepared_execution: PreparedShardExecution,
    *,
    events: EventStream,
    phase: str,
) -> ShardRuntimeResult:
    counters: dict[str, int] = {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0}
    stats_tests_total = 0
    result_tests_total: int | None = None
    timed_out = False
    found_default_database_target = False
    repetitive_pattern: str | None = None

    with open(prepared_execution.log_file, "w") as log_handle:
        log_handle.write(f"Command: {' '.join(prepared_execution.redacted_command)}\n")
        log_handle.write(f"Started: {datetime.now()}\n")
        log_handle.write("=" * 80 + "\n\n")
        log_handle.flush()
        try:
            events.emit(
                "shard_started",
                phase=phase,
                modules=prepared_execution.modules_to_install,
                db=prepared_execution.db_name,
                tags=prepared_execution.test_tags,
            )
        except OSError as exc:
            _logger.debug("executor: failed to emit shard_started (%s)", exc)

        process = subprocess.Popen(
            prepared_execution.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=prepared_execution.compose_environment,
        )
        if process.stdout is None:
            raise RuntimeError("subprocess stdout unavailable")
        stdout = process.stdout

        last_output_time = time.time()
        recent_lines: list[str] = []
        seen_patterns: dict[str, int] = {}
        stall_threshold = 60

        def _terminate_process() -> None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            try:
                subprocess.run(
                    ["docker", "rm", "-f", prepared_execution.container_name],
                    capture_output=True,
                    env=prepared_execution.compose_environment,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                pass

        def _reader() -> None:
            nonlocal stats_tests_total, result_tests_total, last_output_time, found_default_database_target, repetitive_pattern
            for raw_line in iter(stdout.readline, ""):
                line = raw_line.rstrip("\n")
                if contains_default_database_target(line):
                    found_default_database_target = True
                log_handle.write(line + "\n")
                if "Ran " in line and " tests in " in line:
                    match = re.search(r"Ran (\d+) tests", line)
                    if match:
                        counters["tests_run"] = int(match.group(1))
                if "odoo.tests.stats:" in line:
                    stats_match = _ODOO_TEST_STATS_RE.search(line)
                    if stats_match:
                        stats_tests_total += int(stats_match.group(1))
                if "odoo.tests.result:" in line:
                    result_counts_match = _ODOO_TEST_RESULT_COUNTS_RE.search(line)
                    if result_counts_match:
                        result_tests_total = int(result_counts_match.group(3))
                        counters["failures"] = max(counters.get("failures", 0), int(result_counts_match.group(1)))
                        counters["errors"] = max(counters.get("errors", 0), int(result_counts_match.group(2)))
                    else:
                        result_match = _ODOO_TEST_RESULT_RE.search(line)
                        if result_match:
                            result_tests_total = int(result_match.group(1))
                failure_type = _match_unittest_header(line)
                if failure_type == "fail":
                    counters["failures"] = int(counters.get("failures", 0)) + 1
                if failure_type == "error":
                    counters["errors"] = int(counters.get("errors", 0)) + 1
                recent_lines.append(line)
                if len(recent_lines) > 20:
                    recent_lines.pop(0)
                current_time = time.time()
                if current_time - last_output_time > stall_threshold:
                    is_stalled, message = _detect_repetitive(recent_lines, seen_patterns)
                    if is_stalled:
                        repetitive_pattern = message
                last_output_time = current_time

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        try:
            if prepared_execution.timeout and prepared_execution.timeout > 0:
                process.wait(timeout=prepared_execution.timeout)
            else:
                process.wait()
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process()
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process()
        reader_thread.join(timeout=5)
        try:
            stdout.close()
        except OSError:
            pass
        if reader_thread.is_alive():
            reader_thread.join(timeout=5)

        return_code = int(process.returncode or 0)
        if timed_out and return_code == 0:
            return_code = 1
        if found_default_database_target:
            return_code = 1

    if result_tests_total is not None:
        counters["tests_run"] = max(counters.get("tests_run", 0), result_tests_total)
    if stats_tests_total:
        counters["tests_run"] = max(counters.get("tests_run", 0), stats_tests_total)

    return ShardRuntimeResult(
        returncode=return_code,
        counters=counters,
        stats_tests_total=stats_tests_total,
        result_tests_total=result_tests_total,
        timed_out=timed_out,
        default_database_target=found_default_database_target,
        repetitive_pattern=repetitive_pattern,
    )


class OdooExecutor:
    def __init__(self, session_dir: Path, category: str) -> None:
        self.session_dir = session_dir
        self.category = category
        self.settings = TestSettings()
        self._events = EventStream((self.session_dir / "events.ndjson"), echo=self.settings.events_stdout)

    def _phase_dir(self) -> Path:
        phase_dir = self.session_dir / self.category
        phase_dir.mkdir(parents=True, exist_ok=True)
        return phase_dir

    def run(
        self,
        *,
        test_tags: str,
        db_name: str,
        modules_to_install: list[str],
        timeout: int,
        is_tour_test: bool = False,
        is_js_test: bool = False,
        use_production_clone: bool = False,
        template_db: str | None = None,
        use_module_prefix: bool = False,
        extra_env: dict[str, str] | None = None,
        shard_label: str | None = None,
    ) -> ExecResult:
        request = ShardExecutionRequest(
            test_tags=test_tags,
            db_name=db_name,
            modules_to_install=tuple(modules_to_install),
            timeout=timeout,
            is_tour_test=is_tour_test,
            is_js_test=is_js_test,
            use_production_clone=use_production_clone,
            template_db=template_db,
            use_module_prefix=use_module_prefix,
            extra_env=extra_env,
            shard_label=shard_label,
        )
        return self.run_request(request)

    def run_request(self, request: ShardExecutionRequest) -> ExecResult:
        prepared_execution = self._prepare_execution(request)
        print(f"[command] {' '.join(prepared_execution.redacted_command)}")
        print(f"[logs] {prepared_execution.phase_dir}")

        start_time = time.time()
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "command": prepared_execution.redacted_command,
            "test_type": prepared_execution.test_type,
            "category": self.category,
            "database": request.db_name,
            "modules": list(request.modules_to_install),
            "test_tags": prepared_execution.test_tags,
            "timeout": prepared_execution.timeout,
            "start_time": start_time,
            "log_file": str(prepared_execution.log_file),
            "summary_file": str(prepared_execution.summary_file),
            "container_name": prepared_execution.container_name,
        }

        try:
            runtime = _run_prepared_execution(prepared_execution, events=self._events, phase=self.category)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            runtime = ShardRuntimeResult(returncode=1, counters={"tests_run": 0, "failures": 0, "errors": 0, "skips": 0}, error=str(error))
            _logger.error("executor: test execution failed (%s)", error)

        elapsed = time.time() - start_time
        expected_tests = _count_expected_tests(self.category, list(request.modules_to_install))
        outcome = _classify_outcome(runtime, expected_tests=expected_tests)

        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": outcome.returncode,
                "success": outcome.success,
                "counters": runtime.counters,
                "database_flags": prepared_execution.sanitized_database_flags,
                "memory_limit_flags": prepared_execution.memory_limit_flags,
                "test_profile": (prepared_execution.compose_environment.get("TESTKIT_PROFILE") or "default").strip() or "default",
                "odoo_workers": prepared_execution.worker_count,
                "odoo_dev_mode": prepared_execution.development_mode,
                "outcome_kind": outcome.outcome_kind,
                "failure_reasons": list(outcome.failure_reasons),
            }
        )
        if runtime.timed_out:
            summary["timed_out"] = True
        if runtime.repetitive_pattern:
            summary["repetitive_pattern"] = runtime.repetitive_pattern
        if runtime.default_database_target:
            summary["database_target_error"] = (
                "Detected default@default database target in shard logs. "
                "This indicates missing DB configuration propagation."
            )
        if runtime.error:
            summary["error"] = runtime.error
        if outcome.expected_tests:
            summary["expected_tests"] = outcome.expected_tests
        if outcome.missing_tests:
            summary["missing_tests"] = outcome.missing_tests
            print(
                f"[warn] No tests executed for {self.category} ({', '.join(request.modules_to_install)}); "
                f"expected {outcome.expected_tests}."
            )

        with open(prepared_execution.summary_file, "w") as summary_handle:
            json.dump(summary, summary_handle, indent=2, default=str)
        try:
            write_junit_for_shard(prepared_execution.summary_file, prepared_execution.log_file)
        except (OSError, ValueError) as exc:
            _logger.debug("executor: failed to write junit (%s)", exc)
        try:
            self._events.emit(
                "shard_finished",
                phase=self.category,
                modules=list(request.modules_to_install),
                db=request.db_name,
                rc=outcome.returncode,
                elapsed=elapsed,
                outcome=outcome.outcome_kind,
            )
        except OSError as exc:
            _logger.debug("executor: failed to emit shard_finished (%s)", exc)
        return ExecResult(outcome.returncode, prepared_execution.log_file, prepared_execution.summary_file)

    def _prepare_execution(self, request: ShardExecutionRequest) -> PreparedShardExecution:
        script_runner_service = get_script_runner_service()
        disable_dev_mode_raw = os.environ.get("TESTKIT_DISABLE_DEV_MODE")
        skip_autoreload = disable_dev_mode_raw is None or _is_truthy(disable_dev_mode_raw)
        test_tags_final, use_module_prefix = _resolve_test_tags(self.settings, request)
        print(f"[tags] Final test tags: {test_tags_final}")

        install_modules, update_modules = _prepare_database_state(self.settings, request, test_tags_final=test_tags_final)
        shard_base = _shard_base(
            list(request.modules_to_install),
            use_module_prefix=use_module_prefix,
            shard_label=request.shard_label,
        )

        coverage_run: CoverageRun | None = build_coverage_run(self.settings, self.session_dir, list(request.modules_to_install))
        combined_env: dict[str, str] = {}
        if coverage_run:
            combined_env.update(coverage_run.environment)
        if request.extra_env:
            combined_env.update({key: value for key, value in request.extra_env.items() if value is not None})
        combined_env["PYTHONPATH"] = _prepend_pythonpath(
            combined_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH"),
            _TESTKIT_PYTHONPATH,
        )

        resolved_compose_environment = compose_env()
        database_connection_flags = resolve_database_connection_flags(resolved_compose_environment)
        limit_memory_flags = _resolve_limit_memory_flags(resolved_compose_environment)
        worker_count, development_mode = _resolve_worker_settings(
            self.settings,
            request,
            skip_autoreload=skip_autoreload,
        )

        project_name = (resolved_compose_environment.get("ODOO_PROJECT_NAME") or "").strip()
        if not project_name:
            project_name = (os.environ.get("ODOO_PROJECT_NAME") or os.environ.get("ODOO_STACK_NAME") or "").strip()
        project_prefix = f"{project_name}-" if project_name else ""
        run_container_name = _sanitize_container_name(
            f"{project_prefix}testkit-{self.category}-{shard_base}-{os.getpid()}-{uuid4().hex[:6]}"
        )

        command = ["docker", "compose", "run", "--rm", "--no-deps", "--name", run_container_name]
        if coverage_run:
            host_session_dir = coverage_run.data_directory.parent.resolve()
            container_session_dir = str(Path(coverage_run.container_directory).parent)
            command.extend(["-v", f"{host_session_dir}:{container_session_dir}"])
        if combined_env:
            for env_key, env_value in combined_env.items():
                command.extend(["-e", f"{env_key}={env_value}"])
        for env_var in ("JS_PRECHECK", "JS_DEBUG", "TOUR_TIMEOUT", "HOOT_RETRY"):
            override_value = os.environ.get(env_var)
            if override_value:
                command.extend(["-e", f"{env_var}={override_value}"])

        runner_command: list[str]
        if request.is_tour_test or request.is_js_test:
            runner_command = [
                "/odoo/odoo-bin",
                "-d",
                request.db_name,
                "--load=web",
            ]
            if install_modules:
                runner_command.extend(["-i", ",".join(install_modules)])
            if update_modules:
                runner_command.extend(["-u", ",".join(update_modules)])
            runner_command.extend(
                [
                    "--test-tags",
                    test_tags_final,
                    "--test-enable",
                    "--stop-after-init",
                    "--max-cron-threads=0",
                    f"--workers={worker_count}",
                    f"--db-filter=^{request.db_name}$",
                    "--log-level=test",
                    "--without-demo",
                ]
            )
            runner_command.extend(database_connection_flags)
            runner_command.extend(limit_memory_flags)
            if coverage_run:
                runner_command = coverage_run.command_prefix + runner_command
            command.extend([script_runner_service, *runner_command])
            command.append("--dev=none" if skip_autoreload else "--dev=assets")
        else:
            runner_command = [
                "/odoo/odoo-bin",
                "-d",
                request.db_name,
                "--test-tags",
                test_tags_final,
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",
                f"--db-filter=^{request.db_name}$",
                "--log-level=test",
                "--without-demo",
            ]
            runner_command.extend(database_connection_flags)
            runner_command.extend(limit_memory_flags)
            if install_modules:
                runner_command.extend(["-i", ",".join(install_modules)])
            if update_modules:
                runner_command.extend(["-u", ",".join(update_modules)])
            if coverage_run:
                runner_command = coverage_run.command_prefix + runner_command
            command.extend([script_runner_service, *runner_command])
            if skip_autoreload:
                command.append("--dev=none")

        shard_timeout = int(self.settings.shard_timeout)
        timeout = request.timeout
        if shard_timeout and shard_timeout > 0 and (timeout <= 0 or shard_timeout < timeout):
            timeout = shard_timeout

        phase_dir = self._phase_dir()
        log_file = phase_dir / f"{shard_base}.log"
        summary_file = phase_dir / f"{shard_base}.summary.json"
        redacted = _redact_command_for_logging(command)
        sanitized_database_flags = _sanitize_database_flags_for_summary(database_connection_flags)
        test_type = "tour" if request.is_tour_test else ("js" if request.is_js_test else "unit/integration")

        return PreparedShardExecution(
            command=command,
            compose_environment=resolved_compose_environment,
            database_flags=database_connection_flags,
            sanitized_database_flags=sanitized_database_flags,
            memory_limit_flags=limit_memory_flags,
            redacted_command=redacted,
            phase_dir=phase_dir,
            log_file=log_file,
            summary_file=summary_file,
            container_name=run_container_name,
            db_name=request.db_name,
            test_tags=test_tags_final,
            modules_to_install=list(request.modules_to_install),
            worker_count=worker_count,
            development_mode=development_mode,
            timeout=timeout,
            test_type=test_type,
        )
