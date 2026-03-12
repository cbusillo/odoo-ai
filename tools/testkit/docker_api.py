import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from tools.environment_files import discover_repo_root, parse_env_file
from tools.platform import environment as platform_environment

DATABASE_SERVICE = "database"
_SCRIPT_RUNNER_SERVICE_BY_PROJECT: dict[str, str] = {}
_SERVICE_ENSURE_LOCK = threading.Lock()


def _last_output_line(result_output: str | None) -> str:
    if not result_output:
        return ""
    lines = [line.strip() for line in result_output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _resolve_env_file(env: dict[str, str]) -> Path | None:
    raw_value = _blank_to_none(env.get("TESTKIT_ENV_FILE"))
    if not raw_value:
        return None
    env_path = Path(os.path.expandvars(os.path.expanduser(raw_value))).resolve()
    if not env_path.exists():
        raise FileNotFoundError(f"TESTKIT_ENV_FILE not found: {env_path}")
    return env_path


def _require_stack_context(env: dict[str, str]) -> None:
    stack_name = _blank_to_none(env.get("ODOO_STACK_NAME"))
    project_name = _blank_to_none(env.get("ODOO_PROJECT_NAME"))
    if stack_name or project_name:
        return
    raise RuntimeError("Testkit requires a stack context. Provide --stack/--env-file or set ODOO_STACK_NAME/ODOO_PROJECT_NAME.")


def compose_env() -> dict[str, str]:
    """Return an env dict suitable for `docker compose`.

    Testkit shells out to `docker compose` directly (instead of going through the
    deployer stack helpers). Compose variable interpolation relies on the
    process environment (and/or `.env`).

    In local setups we often keep `ODOO_STATE_ROOT=~/...` in `.env`, which
    Docker Compose does not expand. We normalize it to absolute paths and
    ensure the bind-mount variables used in `docker-compose.yml` are set.
    """

    env = os.environ.copy()
    stack_override = _blank_to_none(env.get("ODOO_STACK_NAME"))
    env_file_path = _resolve_env_file(env)
    if env_file_path:
        env.update(parse_env_file(env_file_path))
    else:
        dotenv_path = Path.cwd() / ".env"
        if dotenv_path.exists():
            env.update(parse_env_file(dotenv_path))

    _require_stack_context(env)

    if stack_override:
        env["ODOO_STACK_NAME"] = stack_override

    if _is_truthy(env.get("TESTKIT_DISABLE_DEV_MODE")):
        env.pop("ODOO_DEV_MODE", None)

    stack_name = _blank_to_none(env.get("ODOO_STACK_NAME"))
    project_name = (_blank_to_none(env.get("ODOO_PROJECT_NAME")) or stack_name or "odoo").strip()
    state_root_raw = _blank_to_none(env.get("ODOO_STATE_ROOT"))
    if state_root_raw is None:
        repo_root = discover_repo_root(Path.cwd())
        state_root_raw = str(
            platform_environment.default_local_state_path(
                repo_root=repo_root,
                stack_name=stack_name,
                project_name=project_name,
            )
        )
    state_root_path = Path(os.path.expandvars(os.path.expanduser(state_root_raw))).resolve()

    data_dir_host_raw = _blank_to_none(env.get("ODOO_DATA_HOST_DIR"))
    log_dir_host_raw = _blank_to_none(env.get("ODOO_LOG_HOST_DIR"))
    db_dir_host_raw = _blank_to_none(env.get("ODOO_DB_HOST_DIR"))

    data_dir_host = (
        Path(os.path.expandvars(os.path.expanduser(data_dir_host_raw))).resolve()
        if data_dir_host_raw
        else (state_root_path / "data")
    )
    log_dir_host = (
        Path(os.path.expandvars(os.path.expanduser(log_dir_host_raw))).resolve() if log_dir_host_raw else (state_root_path / "logs")
    )
    db_dir_host = (
        Path(os.path.expandvars(os.path.expanduser(db_dir_host_raw))).resolve()
        if db_dir_host_raw
        else (state_root_path / "postgres")
    )

    env["ODOO_STATE_ROOT"] = str(state_root_path)
    env["ODOO_PROJECT_NAME"] = project_name
    env["ODOO_DATA_HOST_DIR"] = str(data_dir_host)
    env["ODOO_LOG_HOST_DIR"] = str(log_dir_host)
    env["ODOO_DB_HOST_DIR"] = str(db_dir_host)
    env.setdefault("ODOO_DATA_MOUNT", str(data_dir_host))
    env.setdefault("ODOO_LOG_MOUNT", str(log_dir_host))
    env.setdefault("ODOO_DB_MOUNT", str(db_dir_host))

    stack_name = _blank_to_none(env.get("ODOO_STACK_NAME"))
    stack_segments = [segment for segment in stack_name.split("-") if segment] if stack_name else []
    stack_is_ci = "ci" in stack_segments

    db_volume_mode = _blank_to_none(env.get("TESTKIT_DB_VOLUME_MODE"))
    if not db_volume_mode and sys.platform == "darwin" and stack_is_ci:
        db_volume_mode = "named"
    if db_volume_mode == "named":
        volume_name = _blank_to_none(env.get("TESTKIT_DB_VOLUME_NAME")) or "testkit_db"
        env["TESTKIT_DB_VOLUME_MODE"] = "named"
        env["TESTKIT_DB_VOLUME_NAME"] = volume_name
        env["ODOO_DB_MOUNT"] = volume_name

    data_volume_mode = _blank_to_none(env.get("TESTKIT_DATA_VOLUME_MODE"))
    if not data_volume_mode and sys.platform == "darwin" and stack_is_ci:
        data_volume_mode = "named"
    if data_volume_mode == "named":
        volume_name = _blank_to_none(env.get("TESTKIT_DATA_VOLUME_NAME")) or "testkit_data"
        env["TESTKIT_DATA_VOLUME_MODE"] = "named"
        env["TESTKIT_DATA_VOLUME_NAME"] = volume_name
        env["ODOO_DATA_MOUNT"] = volume_name

    log_volume_mode = _blank_to_none(env.get("TESTKIT_LOG_VOLUME_MODE"))
    if not log_volume_mode and sys.platform == "darwin" and stack_is_ci:
        log_volume_mode = "named"
    if log_volume_mode == "named":
        volume_name = _blank_to_none(env.get("TESTKIT_LOG_VOLUME_NAME")) or "testkit_logs"
        env["TESTKIT_LOG_VOLUME_MODE"] = "named"
        env["TESTKIT_LOG_VOLUME_NAME"] = volume_name
        env["ODOO_LOG_MOUNT"] = volume_name
    env.setdefault("COMPOSE_INTERACTIVE_NO_CLI", "1")
    env.setdefault("COMPOSE_MENU", "false")
    return env


def cleanup_testkit_db_volume() -> None:
    env = compose_env()
    if not _is_truthy(env.get("TESTKIT_VOLUME_CLEANUP")) and not _is_truthy(env.get("TESTKIT_DB_VOLUME_CLEANUP")):
        return
    project_name = (_blank_to_none(env.get("ODOO_PROJECT_NAME")) or "odoo").strip()
    volume_name = _blank_to_none(env.get("TESTKIT_DB_VOLUME_NAME")) or "testkit_db"
    _remove_named_volume(project_name, volume_name)


def ensure_named_volume_permissions() -> None:
    env = compose_env()
    data_directory = _blank_to_none(env.get("ODOO_DATA_DIR")) or "/volumes/data"
    log_directory = _blank_to_none(env.get("ODOO_LOG_DIR")) or "/volumes/logs"
    paths = [data_directory, f"{data_directory}/filestore", log_directory]
    deduped_paths: list[str] = []
    for path in paths:
        if path not in deduped_paths:
            deduped_paths.append(path)
    quoted_paths = " ".join(shlex.quote(path) for path in deduped_paths)
    service = get_script_runner_service()

    probe_command = [
        "docker",
        "compose",
        "exec",
        "-T",
        service,
        "/bin/bash",
        "-lc",
        (
            "set -euo pipefail; "
            f"for path in {quoted_paths}; do "
            "mkdir -p \"$path\"; "
            "probe_path=\"$path/.testkit_probe_$$\"; "
            "mkdir -p \"$probe_path\"; "
            "rmdir \"$probe_path\"; "
            "done"
        ),
    ]

    try:
        probe_result = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Timed out while probing testkit volume permissions") from error
    if probe_result.returncode == 0:
        return

    # The runtime image uses a non-root service user. Named volumes are created
    # as root-owned, so template DB creation can fail on filestore writes unless
    # we normalize ownership first.
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "--user",
        "root",
        service,
        "/bin/bash",
        "-lc",
        (
            "set -euo pipefail; "
            f"mkdir -p {quoted_paths}; "
            f"chown ubuntu:ubuntu {quoted_paths}; "
            f"chmod ug+rwX {quoted_paths}"
        ),
    ]
    try:
        normalization_result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=45)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Timed out while normalizing testkit volume permissions") from error
    if normalization_result.returncode != 0:
        detail = _last_output_line(normalization_result.stderr) or _last_output_line(normalization_result.stdout)
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Failed to normalize testkit volume permissions{suffix}")

    verification_result = subprocess.run(
        probe_command,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    if verification_result.returncode != 0:
        detail = _last_output_line(verification_result.stderr) or _last_output_line(verification_result.stdout)
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Testkit volume permissions remain unwritable after normalization{suffix}")


def cleanup_testkit_named_volumes() -> None:
    env = compose_env()
    cleanup_all = _is_truthy(env.get("TESTKIT_VOLUME_CLEANUP"))
    project_name = (_blank_to_none(env.get("ODOO_PROJECT_NAME")) or "odoo").strip()
    volume_specs = (
        ("TESTKIT_DB_VOLUME_CLEANUP", "TESTKIT_DB_VOLUME_NAME", "testkit_db"),
        ("TESTKIT_DATA_VOLUME_CLEANUP", "TESTKIT_DATA_VOLUME_NAME", "testkit_data"),
        ("TESTKIT_LOG_VOLUME_CLEANUP", "TESTKIT_LOG_VOLUME_NAME", "testkit_logs"),
    )
    for cleanup_flag, name_env, default_name in volume_specs:
        if not cleanup_all and not _is_truthy(env.get(cleanup_flag)):
            continue
        volume_name = _blank_to_none(env.get(name_env)) or default_name
        _remove_named_volume(project_name, volume_name)


def _remove_named_volume(project_name: str, volume_name: str) -> None:
    full_name = f"{project_name}_{volume_name}"
    subprocess.run(["docker", "volume", "rm", "-f", full_name], capture_output=True)


def cleanup_orphan_testkit_containers() -> dict[str, object]:
    env = compose_env()
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=testkit-", "--filter", "status=exited", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"removed": []}
    if result.returncode != 0:
        return {"removed": []}
    names = [name.strip() for name in (result.stdout or "").splitlines() if name.strip()]
    removed: list[str] = []
    for name in names:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, env=env, timeout=10)
        except subprocess.TimeoutExpired:
            continue
        removed.append(name)
    return {"removed": removed}


def get_script_runner_service() -> str:
    env = compose_env()
    project_name = (_blank_to_none(env.get("ODOO_PROJECT_NAME")) or "odoo").strip()
    cached_service = _SCRIPT_RUNNER_SERVICE_BY_PROJECT.get(project_name)
    if cached_service:
        return cached_service
    result = subprocess.run(
        ["docker", "compose", "ps", "--services"],
        capture_output=True,
        text=True,
        env=env,
    )
    services = [service.strip() for service in (result.stdout or "").splitlines() if service.strip()] if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            _SCRIPT_RUNNER_SERVICE_BY_PROJECT[project_name] = service
            return service
    if services:
        _SCRIPT_RUNNER_SERVICE_BY_PROJECT[project_name] = "script-runner"
    return "script-runner"


def get_database_service() -> str:
    return DATABASE_SERVICE


def compose_exec(
    service: str,
    args: list[str],
    *,
    capture_output: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    command = ["docker", "compose", "exec", "-T", service] + args
    return subprocess.run(command, capture_output=capture_output, text=True, env=compose_env(), timeout=timeout)


def ensure_services_up(services: list[str]) -> None:
    env = compose_env()
    with _SERVICE_ENSURE_LOCK:
        for service_name in services:
            try:
                running_result = subprocess.run(
                    ["docker", "compose", "ps", "--status", "running", "-q", service_name],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10,
                )
                if running_result.returncode != 0:
                    detail = _last_output_line(running_result.stderr) or _last_output_line(running_result.stdout)
                    suffix = f": {detail}" if detail else ""
                    raise RuntimeError(f"Unable to inspect service status for '{service_name}'{suffix}")
                if running_result.stdout.strip():
                    continue
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(f"Timed out while checking service status: {service_name}") from error
            try:
                start_result = subprocess.run(
                    ["docker", "compose", "up", "-d", service_name],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=60,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(f"Timed out while starting service: {service_name}") from error
            if start_result.returncode != 0:
                details = (start_result.stderr or start_result.stdout or "").strip()
                message = f"Failed to start service: {service_name}"
                if details:
                    message = f"{message}: {details}"
                raise RuntimeError(message)
