import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .auth import setup_test_authentication
from .browser import kill_browsers_and_zombies, restart_script_runner_with_orphan_cleanup
from .db import (
    clone_production_database,
    drop_and_create,
    drop_and_create_test_database,
    get_production_db_name,
)
from .docker_api import compose_env, get_script_runner_service
from .filestore import cleanup_single_test_filestore, filestore_exists, snapshot_filestore
from .reporter import write_junit_for_shard
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings

_logger = logging.getLogger(__name__)


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


@dataclass
class ExecResult:
    returncode: int
    log_file: Path
    summary_file: Path


class OdooExecutor:
    def __init__(self, session_dir: Path, category: str) -> None:
        self.session_dir = session_dir
        self.category = category
        self.settings = TestSettings()
        # Events stream (optional)
        from .events import EventStream

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
        script_runner_service = get_script_runner_service()
        modules_str = ",".join(modules_to_install)

        # tags override
        test_tags_override = (self.settings.test_tags_override or "").strip()
        if test_tags_override:
            if is_tour_test:
                must = "tour_test"
            elif is_js_test:
                must = "js_test"
            elif test_tags and "integration" in test_tags:
                must = "integration_test"
            else:
                must = "unit_test"
            tag_parts: list[str] = []
            if must and must not in test_tags_override:
                tag_parts.append(must)
            tag_parts.append(test_tags_override)
            test_tags_final = ",".join(tag_part for tag_part in tag_parts if tag_part)
            use_module_prefix = False
            print(f"🎯 Using TEST_TAGS override: {test_tags_final}")
        else:
            if not test_tags:
                test_tags_final = ",".join([f"/{module_name}" for module_name in modules_to_install])
            elif not use_module_prefix:
                test_tags_final = test_tags
            else:
                tag_parts = [tag_part.strip() for tag_part in test_tags.split(",") if tag_part.strip()]
                if len(tag_parts) == 1 and not tag_parts[0].startswith("-"):
                    tag = tag_parts[0]
                    test_tags_final = ",".join([f"{tag}/{module_name}" for module_name in modules_to_install])
                else:
                    primary_tag = next(
                        (tag_part for tag_part in reversed(tag_parts) if not tag_part.startswith("-")),
                        tag_parts[-1],
                    )
                    scoped_tags = [f"{primary_tag}/{module_name}" for module_name in modules_to_install]
                    kept_tags = [tag_part for tag_part in tag_parts if tag_part != primary_tag]
                    test_tags_final = ",".join(kept_tags + scoped_tags)

        print(f"🏷️  Final test tags: {test_tags_final}")

        # Pre-run DB/filestore setup
        restart_script_runner_with_orphan_cleanup()
        if is_js_test or is_tour_test:
            kill_browsers_and_zombies()
        if use_production_clone:
            if template_db:
                # Fast path: create from template
                drop_and_create(db_name, template_db)
            else:
                clone_production_database(db_name)
            # Filestore snapshot control
            need_filestore = is_tour_test or ("tour" in test_tags) or ("integration" in test_tags)
            if need_filestore:
                skip_fs = self.settings.skip_filestore_tour if is_tour_test else self.settings.skip_filestore_integration
                if not skip_fs and not filestore_exists(db_name):
                    snapshot_filestore(db_name, get_production_db_name())
                kill_browsers_and_zombies()
        else:
            try:
                cleanup_single_test_filestore(db_name)
            except OSError as exc:
                _logger.debug("executor: failed to cleanup filestore %s (%s)", db_name, exc)
            drop_and_create_test_database(db_name)
            if is_js_test or is_tour_test:
                setup_test_authentication(db_name)

        module_flag = "-u" if use_production_clone else "-i"

        command = ["docker", "compose", "run", "--rm"]
        # Per-shard environment injection (for slicer etc.)
        if extra_env:
            for env_key, env_value in extra_env.items():
                if env_value is None:
                    continue
                command.extend(["-e", f"{env_key}={env_value}"])
        # pass-through debug/timeouts
        for env_var in ("JS_PRECHECK", "JS_DEBUG", "TOUR_TIMEOUT"):
            env_value = os.environ.get(env_var)
            if env_value:
                command.extend(["-e", f"{env_var}={env_value}"])

        if is_tour_test or is_js_test:
            tour_workers_default = int(self.settings.tour_workers)
            js_workers_default = int(self.settings.js_workers)
            if is_tour_test or is_js_test:
                command.extend(["-e", f"TOUR_WARMUP={self.settings.tour_warmup}"])
            command.extend(
                [
                    script_runner_service,
                    "/odoo/odoo-bin",
                    "-d",
                    db_name,
                    "--load=web",
                    module_flag,
                    modules_str,
                    "--test-tags",
                    test_tags_final,
                    "--test-enable",
                    "--stop-after-init",
                    "--max-cron-threads=0",
                    f"--workers={js_workers_default if is_js_test else tour_workers_default}",
                    f"--db-filter=^{db_name}$",
                    "--log-level=test",
                    "--without-demo=all",
                ]
            )
            if is_tour_test:
                command.append("--dev=assets")
        else:
            command.extend(
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
                    "--workers=0",
                    f"--db-filter=^{db_name}$",
                    "--log-level=test",
                    "--without-demo=all",
                ]
            )

        phase_dir = self._phase_dir()

        def _shard_base(module_names: list[str]) -> str:
            if use_module_prefix and len(module_names) == 1:
                return module_names[0]
            module_key = ",".join(sorted(module_names))
            import hashlib

            hash_prefix = hashlib.sha1(module_key.encode()).hexdigest()[:8]
            return f"shard-{hash_prefix}"

        shard_base = _shard_base(modules_to_install)
        if shard_label:
            shard_base = f"{shard_base}-{shard_label}"
        log_file = phase_dir / f"{shard_base}.log"
        summary_file = phase_dir / f"{shard_base}.summary.json"

        # redacted echo
        redacted = []
        index = 0
        secret_prefixes = ("ODOO_TEST_PASSWORD=", "PASSWORD=", "TOKEN=", "KEY=")
        while index < len(command):
            part = command[index]
            if part == "-e" and index + 1 < len(command):
                env_pair = command[index + 1]
                for secret_prefix in secret_prefixes:
                    if env_pair.startswith(secret_prefix):
                        env_pair = secret_prefix + "***"
                        break
                redacted.extend([part, env_pair])
                index += 2
                continue
            redacted.append(part)
            index += 1

        # Secret hygiene: redaction already applied; avoid echoing any naked env pairs in logs
        print(f"🚀 Command: {' '.join(redacted)}")
        print(f"📁 Logs: {phase_dir}")

        start_time = time.time()
        counters: dict[str, int] = {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0}
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "command": command,
            "test_type": "tour" if is_tour_test else ("js" if is_js_test else "unit/integration"),
            "category": self.category,
            "database": db_name,
            "modules": modules_to_install,
            "test_tags": test_tags_final,
            "timeout": timeout,
            "start_time": start_time,
            "log_file": str(log_file),
            "summary_file": str(summary_file),
            "counters": counters,
        }

        try:
            with open(log_file, "w") as log_handle:
                log_handle.write(f"Command: {' '.join(redacted)}\n")
                log_handle.write(f"Started: {datetime.now()}\n")
                log_handle.write("=" * 80 + "\n\n")
                log_handle.flush()
                try:
                    self._events.emit(
                        "shard_started",
                        phase=self.category,
                        modules=modules_to_install,
                        db=db_name,
                        tags=test_tags_final,
                    )
                except OSError as exc:
                    _logger.debug("executor: failed to emit shard_started (%s)", exc)
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=compose_env(),
                )
                assert process.stdout is not None
                stdout = process.stdout

                last_output_time = time.time()
                recent_lines: list[str] = []
                seen_patterns: dict[str, int] = {}
                stall_threshold = 60

                for raw_line in iter(stdout.readline, ""):
                    line = raw_line.rstrip("\n")
                    log_handle.write(line + "\n")
                    # counters heuristic from Odoo test output
                    if "Ran " in line and " tests in " in line:
                        match = re.search(r"Ran (\d+) tests", line)
                        if match:
                            counters["tests_run"] = int(match.group(1))
                    if line.startswith("FAIL:"):
                        counters["failures"] = int(counters.get("failures", 0)) + 1
                    if line.startswith("ERROR:"):
                        counters["errors"] = int(counters.get("errors", 0)) + 1
                    # repetitive detection
                    recent_lines.append(line)
                    if len(recent_lines) > 20:
                        recent_lines.pop(0)
                    current_time = time.time()
                    if current_time - last_output_time > stall_threshold:
                        is_stalled, message = _detect_repetitive(recent_lines, seen_patterns)
                        if is_stalled:
                            summary["repetitive_pattern"] = message
                    last_output_time = current_time
                process.wait()
                return_code = int(process.returncode or 0)

        except (OSError, subprocess.SubprocessError) as error:
            summary.update(
                {
                    "end_time": time.time(),
                    "elapsed_seconds": time.time() - start_time,
                    "returncode": 1,
                    "success": False,
                    "error": str(error),
                }
            )
            _logger.error("executor: test execution failed (%s)", error)
            with open(summary_file, "w") as summary_handle:
                json.dump(summary, summary_handle, indent=2, default=str)
            return ExecResult(1, log_file, summary_file)

        elapsed = time.time() - start_time
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": return_code,
                "success": return_code == 0,
            }
        )
        with open(summary_file, "w") as summary_handle:
            json.dump(summary, summary_handle, indent=2, default=str)
        try:
            write_junit_for_shard(summary_file, log_file)
        except (OSError, ValueError) as exc:
            _logger.debug("executor: failed to write junit (%s)", exc)
        try:
            self._events.emit(
                "shard_finished",
                phase=self.category,
                modules=modules_to_install,
                db=db_name,
                rc=return_code,
                elapsed=elapsed,
            )
        except OSError as exc:
            _logger.debug("executor: failed to emit shard_finished (%s)", exc)
        return ExecResult(return_code, log_file, summary_file)
