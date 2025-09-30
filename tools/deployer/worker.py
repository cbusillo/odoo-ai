from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path

from .config import DeploySettings, StackSettings, load_settings
from .gitutils import load_gitmodules
from .queue import iter_queue, load_payload, remove_task

LOGGER = logging.getLogger("deploy.worker")


class DeployError(RuntimeError):
    pass


@dataclass(slots=True)
class TaskContext:
    stack: StackSettings
    payload: dict[str, object]
    gitmodules: dict[str, str]
    settings: DeploySettings


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    LOGGER.debug("$ %s", " ".join(command))
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode != 0:
        raise DeployError(f"Command failed ({result.returncode}): {' '.join(command)}")


def compose_prefix(stack: StackSettings) -> list[str]:
    command = list(stack.docker_compose)
    command += ["-p", stack.project, "--env-file", str(stack.env_file)]
    for compose_file in stack.compose_files:
        command += ["-f", str(compose_file)]
    return command


def pull_repo(path: Path, branch: str) -> None:
    run_command(["git", "fetch", "--prune", "origin"], cwd=path)
    run_command(["git", "reset", "--hard", f"origin/{branch}"], cwd=path)


def resolve_addon_path(context: TaskContext) -> Path:
    repository = str(context.payload.get("repository"))
    entry = context.gitmodules.get(repository)
    if not entry:
        raise DeployError(f"Repository '{repository}' not found in .gitmodules")
    relative = Path(entry)
    candidates: Iterable[Path] = (
        context.stack.addons_root / relative,
        context.stack.addons_root / relative.name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return context.stack.addons_root / relative


def process_task(context: TaskContext) -> None:
    lane = str(context.payload.get("lane"))
    branch = str(context.payload.get("branch"))
    repository = str(context.payload.get("repository"))
    after_sha = str(context.payload.get("after") or "")
    modules = list(context.payload.get("modules") or context.stack.modules_default)
    if not modules:
        raise DeployError(f"No modules configured for repository '{repository}'")

    state_dir = context.stack.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / f"{repository}.{branch}.sha"
    if after_sha and state_file.exists() and state_file.read_text().strip() == after_sha:
        LOGGER.info("Skipping %s@%s — already deployed", repository, after_sha)
        return

    if lane == "core":
        repo_path = context.stack.repo_root
    else:
        repo_path = resolve_addon_path(context)

    LOGGER.info("Syncing %s (%s) -> %s", repository, branch, repo_path)
    pull_repo(repo_path, branch)

    compose_cmd = compose_prefix(context.stack)
    if lane == "addon" and context.stack.addons_root == context.stack.repo_root:
        LOGGER.debug("Addons mounted from repo root; no additional bind handling required")

    if lane != "core":
        LOGGER.info("Applying addon updates for modules: %s", ", ".join(modules))
    else:
        LOGGER.info("Applying core update; modules: %s", ", ".join(modules))

    if lane in {"addon", "core"}:
        if context.stack.addons_root != context.stack.repo_root and lane == "addon":
            (context.stack.addons_root / "").mkdir(parents=True, exist_ok=True)

    if lane == "addon" and context.stack.queue_dir != context.stack.state_dir:
        LOGGER.debug("Queue dir %s distinct from state dir %s", context.stack.queue_dir, context.stack.state_dir)

    if lane == "addon" and context.stack.project.endswith("dev"):
        up_args = compose_cmd + ["up", "-d", "web", "script-runner"]
        run_command(up_args, cwd=context.stack.repo_root)
    else:
        build_args = compose_cmd + ["build", "--pull", "web", "script-runner"]
        run_command(build_args, cwd=context.stack.repo_root)
        up_args = compose_cmd + ["up", "-d", "web", "script-runner"]
        run_command(up_args, cwd=context.stack.repo_root)

    module_cli = ",".join(sorted(set(modules)))
    upgrade_args = compose_cmd + [
        "exec",
        "-T",
        "script-runner",
        "bash",
        "-lc",
        f"/odoo/odoo-bin -u {module_cli} -d $ODOO_DB_NAME --stop-after-init",
    ]
    run_command(upgrade_args, cwd=context.stack.repo_root)

    curl_args = [
        "curl",
        "-s",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        context.stack.healthcheck_url,
    ]
    LOGGER.info("Health check %s", context.stack.healthcheck_url)
    result = subprocess.run(curl_args, capture_output=True, text=True)
    status_code = result.stdout.strip()
    if result.returncode != 0 or status_code != "200":
        raise DeployError(f"Health check failed ({status_code})")

    health_dir = context.stack.stack_root / ".health"
    health_dir.mkdir(parents=True, exist_ok=True)
    health_payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "status": int(status_code),
        "repository": repository,
        "branch": branch,
        "commit": after_sha,
    }
    (health_dir / "last.json").write_text(json.dumps(health_payload, separators=(",", ":")))

    if after_sha:
        state_file.write_text(after_sha)


@contextmanager
def acquire_lock(lock_path: Path) -> Iterable[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:  # pragma: no cover - release best effort
                pass


def worker_loop(settings: DeploySettings, stack_name: str, *, once: bool) -> None:
    stack = settings.stack_for(stack_name)
    gitmodules = load_gitmodules(settings.gitmodules_path)
    lock_path = stack.stack_root / ".lock" / "deploy.lock"
    with acquire_lock(lock_path):
        while True:
            tasks = iter_queue(stack.queue_dir)
            if not tasks:
                if once:
                    return
                time.sleep(1)
                continue

            processed_any = False
            for task_file in tasks:
                payload = load_payload(task_file)
                if payload.get("stack") != stack.name:
                    continue

                age_seconds = time.time() - task_file.stat().st_mtime
                if stack.debounce_seconds and age_seconds < stack.debounce_seconds:
                    LOGGER.debug(
                        "Debounce active for %s (age %.1fs < %ss)", task_file.name, age_seconds, stack.debounce_seconds
                    )
                    continue

                context = TaskContext(stack=stack, payload=payload, gitmodules=gitmodules, settings=settings)
                try:
                    process_task(context)
                except DeployError as exc:
                    LOGGER.error("Task %s failed: %s", task_file.name, exc)
                    return
                else:
                    remove_task(task_file)
                    processed_any = True
                    LOGGER.info("Completed task %s", task_file.name)
                    if once:
                        return

            if not processed_any:
                time.sleep(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stack deploy worker")
    parser.add_argument("--config", type=Path, required=True, help="Deployment settings YAML path")
    parser.add_argument("--stack", required=True, help="Stack name (e.g. opw-testing)")
    parser.add_argument("--once", action="store_true", help="Process a single eligible task and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(args.verbose)
    settings = load_settings(args.config)
    worker_loop(settings, args.stack, once=args.once)


if __name__ == "__main__":  # pragma: no cover
    main()
