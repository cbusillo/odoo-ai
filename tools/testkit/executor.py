from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from collections.abc import Iterable
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
from .docker_api import get_script_runner_service
from .filestore import cleanup_single_test_filestore, filestore_exists, snapshot_filestore
from .reporter import write_junit_for_shard
from .settings import SUMMARY_SCHEMA_VERSION, TestSettings


def _normalize(line: str) -> str:
    line = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", "[TIMESTAMP]", line)
    line = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[IP]", line)
    line = re.sub(r"\b\d+\b", "[NUM]", line)
    line = re.sub(r"\d+\.\d+(?:-\d+)?", "[VERSION]", line)
    return " ".join(line.split()).strip()


def _detect_repetitive(recent_lines: list[str], seen: dict[str, int], min_occ: int = 5) -> tuple[bool, str]:
    if len(recent_lines) < min_occ:
        return False, ""
    for l in recent_lines:
        n = _normalize(l)
        if n and len(n) > 20:
            seen[n] = seen.get(n, 0) + 1
    if not seen:
        return False, ""
    pattern, count = max(seen.items(), key=lambda x: x[1])
    recent_norm = [_normalize(l) for l in recent_lines]
    ratio = sum(1 for n in recent_norm if n == pattern) / len(recent_norm)
    if count >= min_occ and ratio > 0.7:
        sample = next((l for l in recent_lines if _normalize(l) == pattern), "")
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
        d = self.session_dir / self.category
        d.mkdir(parents=True, exist_ok=True)
        return d

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
            parts = []
            if must and must not in test_tags_override:
                parts.append(must)
            parts.append(test_tags_override)
            test_tags_final = ",".join(p for p in parts if p)
            use_module_prefix = False
            print(f"🎯 Using TEST_TAGS override: {test_tags_final}")
        else:
            if not test_tags:
                test_tags_final = ",".join([f"/{m}" for m in modules_to_install])
            elif not use_module_prefix:
                test_tags_final = test_tags
            else:
                parts = [p.strip() for p in test_tags.split(",") if p.strip()]
                if len(parts) == 1 and not parts[0].startswith("-"):
                    tag = parts[0]
                    test_tags_final = ",".join([f"{tag}/{m}" for m in modules_to_install])
                else:
                    primary = next((p for p in reversed(parts) if not p.startswith("-")), parts[-1])
                    scoped = [f"{primary}/{m}" for m in modules_to_install]
                    keep = [p for p in parts if p != primary]
                    test_tags_final = ",".join(keep + scoped)

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
            # Scoped pre-test cleanup of DB and filestore to avoid cross-run interference
            try:
                cleanup_single_test_filestore(db_name)
            except Exception:
                pass
            drop_and_create_test_database(db_name)
            if is_js_test or is_tour_test:
                setup_test_authentication(db_name)

        module_flag = "-u" if use_production_clone else "-i"

        cmd = ["docker", "compose", "run", "--rm"]
        # pass-through debug/timeouts
        for var in ("JS_PRECHECK", "JS_DEBUG", "TOUR_TIMEOUT"):
            val = os.environ.get(var)
            if val:
                cmd.extend(["-e", f"{var}={val}"])

        if is_tour_test or is_js_test:
            tour_workers_default = int(self.settings.tour_workers)
            js_workers_default = int(self.settings.js_workers)
            if is_tour_test or is_js_test:
                cmd.extend(["-e", f"TOUR_WARMUP={self.settings.tour_warmup}"])
            cmd.extend(
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
                cmd.append("--dev=assets")
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
                    "--workers=0",
                    f"--db-filter=^{db_name}$",
                    "--log-level=test",
                    "--without-demo=all",
                ]
            )

        phase_dir = self._phase_dir()

        def _shard_base(mods: list[str]) -> str:
            if use_module_prefix and len(mods) == 1:
                return mods[0]
            key = ",".join(sorted(mods))
            import hashlib

            hid = hashlib.sha1(key.encode()).hexdigest()[:8]
            return f"shard-{hid}"

        base = _shard_base(modules_to_install)
        log_file = phase_dir / f"{base}.log"
        summary_file = phase_dir / f"{base}.summary.json"

        # redacted echo
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

        # Secret hygiene: redaction already applied; avoid echoing any naked env pairs in logs
        print(f"🚀 Command: {' '.join(redacted)}")
        print(f"📁 Logs: {phase_dir}")

        start_time = time.time()
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "command": cmd,
            "test_type": "tour" if is_tour_test else ("js" if is_js_test else "unit/integration"),
            "category": self.category,
            "database": db_name,
            "modules": modules_to_install,
            "test_tags": test_tags_final,
            "timeout": timeout,
            "start_time": start_time,
            "log_file": str(log_file),
            "summary_file": str(summary_file),
            "counters": {"tests_run": 0, "failures": 0, "errors": 0, "skips": 0},
        }

        try:
            with open(log_file, "w") as lf:
                lf.write(f"Command: {' '.join(redacted)}\n")
                lf.write(f"Started: {datetime.now()}\n")
                lf.write("=" * 80 + "\n\n")
                lf.flush()
                # Emit shard start event
                try:
                    self._events.emit(
                        "shard_started",
                        phase=self.category,
                        modules=modules_to_install,
                        db=db_name,
                        tags=test_tags_final,
                    )
                except Exception:
                    pass
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

                last_out = time.time()
                recent: list[str] = []
                seen: dict[str, int] = {}
                stall_threshold = 60

                for raw in iter(process.stdout.readline, ""):
                    line = raw.rstrip("\n")
                    lf.write(line + "\n")
                    last_out = time.time()
                    # counters heuristic from Odoo test output
                    if "Ran " in line and " tests in " in line:
                        m = re.search(r"Ran (\d+) tests", line)
                        if m:
                            summary["counters"]["tests_run"] = int(m.group(1))
                    if line.startswith("FAIL:"):
                        summary["counters"]["failures"] = int(summary["counters"].get("failures", 0)) + 1
                    if line.startswith("ERROR:"):
                        summary["counters"]["errors"] = int(summary["counters"].get("errors", 0)) + 1
                    # repetitive detection
                    recent.append(line)
                    if len(recent) > 20:
                        recent.pop(0)
                    now = time.time()
                    if now - last_out > stall_threshold:
                        stalled, msg = _detect_repetitive(recent, seen)
                        if stalled:
                            summary["repetitive_pattern"] = msg
                process.wait()
                rc = int(process.returncode or 0)

        except Exception as e:  # pragma: no cover
            summary.update(
                {
                    "end_time": time.time(),
                    "elapsed_seconds": time.time() - start_time,
                    "returncode": 1,
                    "success": False,
                    "error": str(e),
                }
            )
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2, default=str)
            return ExecResult(1, log_file, summary_file)

        elapsed = time.time() - start_time
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": rc,
                "success": rc == 0,
            }
        )
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        try:
            write_junit_for_shard(summary_file, log_file)
        except Exception:
            pass
        try:
            self._events.emit(
                "shard_finished",
                phase=self.category,
                modules=modules_to_install,
                db=db_name,
                rc=rc,
                elapsed=elapsed,
            )
        except Exception:
            pass
        return ExecResult(rc, log_file, summary_file)
