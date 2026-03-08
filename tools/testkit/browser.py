import contextlib
import os
import subprocess
import threading
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix runtimes
    fcntl = None

from .docker_api import compose_env, compose_exec, ensure_services_up, get_script_runner_service

_SCRIPT_RUNNER_RESTART_LOCK = threading.Lock()
_SCRIPT_RUNNER_RESTARTED_PROJECTS: set[str] = set()
_SCRIPT_RUNNER_RESTART_LOCK_FILENAME = ".testkit-script-runner-restart.lock"


def _runtime_project_name(runtime_environment: dict[str, str]) -> str:
    return (
        (runtime_environment.get("ODOO_PROJECT_NAME") or runtime_environment.get("ODOO_STACK_NAME") or "odoo").strip()
        or "odoo"
    )


def _runtime_state_root(runtime_environment: dict[str, str]) -> Path:
    raw_state_root = (runtime_environment.get("ODOO_STATE_ROOT") or "").strip()
    if not raw_state_root:
        return Path.home() / "odoo-ai" / _runtime_project_name(runtime_environment)
    return Path(os.path.expandvars(os.path.expanduser(raw_state_root))).resolve()


@contextlib.contextmanager
def _cross_process_restart_lock(runtime_environment: dict[str, str]):
    if fcntl is None:
        yield
        return

    state_root = _runtime_state_root(runtime_environment)
    state_root.mkdir(parents=True, exist_ok=True)
    lock_file = state_root / _SCRIPT_RUNNER_RESTART_LOCK_FILENAME
    with lock_file.open("w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def reset_script_runner_restart_cache() -> None:
    with _SCRIPT_RUNNER_RESTART_LOCK:
        _SCRIPT_RUNNER_RESTARTED_PROJECTS.clear()


def kill_browsers_and_zombies() -> None:
    service = get_script_runner_service()
    ensure_services_up([service])
    for name in ("chrome", "chromium"):
        compose_exec(service, ["pkill", name])
    for name in ("chrome", "chromium", "geckodriver", "chromedriver"):
        compose_exec(service, ["pkill", "-9", name])
    compose_exec(service, ["sh", "-c", "ps aux | grep defunct | awk '{print $2}' | xargs -r kill -9"])  # noqa: ISC001


def restart_script_runner_with_orphan_cleanup() -> None:
    # Per-shard compose restarts race in parallel test fan-out. We only run this
    # cleanup once per compose project in a process.
    runtime_environment = compose_env()
    project_name = _runtime_project_name(runtime_environment)
    with _cross_process_restart_lock(runtime_environment):
        with _SCRIPT_RUNNER_RESTART_LOCK:
            if project_name in _SCRIPT_RUNNER_RESTARTED_PROJECTS:
                return
            service = get_script_runner_service()
            command = ["docker", "compose", "up", "-d", "--remove-orphans", service]
            try:
                result = subprocess.run(command, capture_output=True, text=True, env=runtime_environment, timeout=60)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    f"Timed out while refreshing testkit service '{service}'. "
                    "Check docker daemon responsiveness and retry."
                ) from error
            if result.returncode != 0:
                details = (result.stderr or result.stdout or "").strip()
                message = f"Failed to refresh testkit service '{service}'"
                if details:
                    message = f"{message}: {details}"
                raise RuntimeError(message)
            _SCRIPT_RUNNER_RESTARTED_PROJECTS.add(project_name)
