import json
import logging
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from .command import CommandError, run_process
from .compose_ops import local_compose, local_compose_command, local_compose_env, remote_compose_command
from .health import HealthcheckError, wait_for_health
from .remote import ensure_remote_directory, run_remote, upload_file
from .settings import AUTO_INSTALLED_SENTINEL, StackSettings, discover_local_modules


def _run_compose(settings: StackSettings, args: list[str], remote: bool) -> None:
    if remote:
        if settings.remote_host is None:
            raise ValueError("remote host missing")
        if settings.remote_stack_path is None:
            raise ValueError("remote stack path missing")
        command = remote_compose_command(settings, args)
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
        return
    local_compose(settings, args)


def build_updated_environment(
    settings: StackSettings, image_reference: str, extra_variables: Mapping[str, str] | None = None
) -> dict[str, str]:
    data = settings.environment.copy()
    data[settings.image_variable_name] = image_reference
    if extra_variables is not None:
        data.update(extra_variables)
    return data


def render_env_content(values: Mapping[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    return "\n".join(lines) + "\n"


def write_env_file(path: Path, values: Mapping[str, str]) -> None:
    content = render_env_content(values)
    path.write_text(content, encoding="utf-8")


def ensure_local_bind_mounts(settings: StackSettings) -> None:
    for path in (settings.data_dir, settings.db_dir, settings.log_dir):
        path.mkdir(parents=True, exist_ok=True)
    session_dir = settings.log_dir / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)


def ensure_remote_bind_mounts(settings: StackSettings) -> None:
    if settings.remote_host is None:
        return
    for path in (settings.data_dir, settings.db_dir, settings.log_dir):
        ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, path)
    session_dir = settings.log_dir / "sessions"
    ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, session_dir)
    # Align permissions so the container user can write to bind mounts.
    state_root = settings.state_root
    if state_root:
        owner_uid = settings.environment.get("ODOO_DATA_UID") or settings.environment.get("DATA_UID") or "1000"
        owner_gid = settings.environment.get("ODOO_DATA_GID") or settings.environment.get("DATA_GID") or owner_uid
        try:
            run_remote(
                settings.remote_host,
                settings.remote_user,
                settings.remote_port,
                ["chown", "-R", f"{owner_uid}:{owner_gid}", str(state_root)],
            )
        except CommandError as error:  # noqa: BLE001  # type: ignore[name-defined]
            logging.getLogger("deploy.remote").warning(
                "unable to chown remote state root %s: %s",
                state_root,
                error,
            )


def push_env_to_remote(settings: StackSettings, env_values: Mapping[str, str]) -> None:
    if settings.remote_host is None:
        raise ValueError("remote host missing")
    if settings.remote_env_path is None:
        raise ValueError("remote env path missing")
    logging.getLogger("deploy.remote").info("uploading env to %s", settings.remote_env_path)
    ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, settings.remote_env_path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(render_env_content(env_values))
    try:
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, temp_path, settings.remote_env_path)
        if settings.remote_stack_path is not None:
            default_env_path = settings.remote_stack_path / ".env"
            if default_env_path != settings.remote_env_path:
                logging.getLogger("deploy.remote").info("copying env to %s", default_env_path)
                ensure_remote_directory(
                    settings.remote_host,
                    settings.remote_user,
                    settings.remote_port,
                    default_env_path.parent,
                )
                run_remote(
                    settings.remote_host,
                    settings.remote_user,
                    settings.remote_port,
                    [
                        "cp",
                        str(settings.remote_env_path),
                        str(default_env_path),
                    ],
                )
    finally:
        temp_path.unlink(missing_ok=True)


def execute_compose_pull(settings: StackSettings, remote: bool) -> None:
    _run_compose(settings, ["pull", *settings.services], remote)


def execute_compose_up(settings: StackSettings, remote: bool) -> None:
    _run_compose(settings, ["up", "-d", *settings.services], remote)


def _wait_for_local_service(settings: StackSettings, service: str, *, timeout_seconds: int = 60) -> None:
    if service not in settings.services:
        return
    start = time.monotonic()
    while True:
        result = run_process(
            local_compose_command(settings, ["ps", "-q", service]),
            cwd=settings.repo_root,
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
        container_id = (result.stdout or "").strip()
        if container_id:
            status = run_process(
                ["docker", "inspect", "-f", "{{.State.Status}}", container_id],
                capture_output=True,
                check=False,
            )
            if (status.stdout or "").strip() == "running":
                return
        if time.monotonic() - start > timeout_seconds:
            raise ValueError(f"Timed out waiting for {service} to be running.")
        time.sleep(2)


def _run_upgrade_with_retry(settings: StackSettings, upgrade_subcommand: list[str], *, remote: bool) -> None:
    if remote:
        _run_compose(settings, upgrade_subcommand, remote)
        return
    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            _run_compose(settings, upgrade_subcommand, remote)
            return
        except CommandError as error:
            message = "\n".join(value for value in (error.stdout or "", error.stderr or "", str(error)) if value)
            if "restarting" not in message and "is not running" not in message:
                raise
            if attempt == max_attempts - 1:
                raise
            _wait_for_local_service(settings, settings.script_runner_service, timeout_seconds=60)
            time.sleep(2)


def execute_upgrade(settings: StackSettings, modules: tuple[str, ...], remote: bool) -> None:
    resolved_modules = modules
    if modules == (AUTO_INSTALLED_SENTINEL,):
        resolved_modules = _installed_local_modules(settings)
    if not resolved_modules:
        raise ValueError("no modules configured for upgrade")
    module_argument = ",".join(dict.fromkeys(resolved_modules))
    upgrade_subcommand = [
        "exec",
        "-T",
        settings.script_runner_service,
        "bash",
        "-lc",
        f"{settings.odoo_bin_path} -u {module_argument} -d $ODOO_DB_NAME --stop-after-init",
    ]
    if not remote and "web" in settings.services:
        _run_compose(settings, ["stop", "web"], remote)
        try:
            _run_compose(settings, ["up", "-d", settings.script_runner_service], remote)
            _wait_for_local_service(settings, settings.script_runner_service, timeout_seconds=60)
            _run_upgrade_with_retry(settings, upgrade_subcommand, remote=remote)
        finally:
            _run_compose(settings, ["up", "-d", "web"], remote)
        return
    if not remote:
        _run_compose(settings, ["up", "-d", settings.script_runner_service], remote)
        _wait_for_local_service(settings, settings.script_runner_service, timeout_seconds=60)
    _run_upgrade_with_retry(settings, upgrade_subcommand, remote=remote)


def _installed_local_modules(settings: StackSettings) -> tuple[str, ...]:
    container_name = f"{settings.compose_project}-database-1"
    db_name = settings.environment.get("ODOO_DB_NAME")
    db_user = settings.environment.get("ODOO_DB_USER")
    db_password = settings.environment.get("ODOO_DB_PASSWORD", "")
    if not db_name or not db_user:
        raise ValueError("ODOO_DB_NAME/ODOO_DB_USER missing for module upgrade")

    query = "select name from ir_module_module where state in ('installed','to upgrade','to install')"
    command = [
        "docker",
        "exec",
        "-i",
        container_name,
        "psql",
        "-qtAX",
        "-U",
        db_user,
        "-d",
        db_name,
        "-c",
        query,
    ]
    env = os.environ.copy()
    if db_password:
        env["PGPASSWORD"] = db_password
    last_error = ""
    for attempt in range(10):
        result = run_process(command, capture_output=True, check=False, env=env)
        if result.returncode == 0:
            break
        last_error = (result.stderr or "").strip()
        time.sleep(2)
    else:
        raise ValueError(f"Failed to query installed modules after retries; database may be restarting. {last_error}")
    installed = {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}
    if not installed:
        return ()
    local_modules = set(discover_local_modules(settings.environment, settings.repo_root))
    return tuple(sorted(installed & local_modules))


def run_health_check(settings: StackSettings, remote: bool, timeout_seconds: int) -> None:
    if remote and settings.remote_host is not None:
        command = ["curl", "-sf", settings.healthcheck_url]
        try:
            run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command)
            return
        except (CommandError, OSError) as error:
            raise HealthcheckError(f"remote health check failed: {error}") from error
    wait_for_health(settings.healthcheck_url, timeout_seconds=timeout_seconds)


def deploy_stack(
    settings: StackSettings,
    image_reference: str,
    remote: bool,
    skip_upgrade: bool = False,
    skip_health_check: bool = False,
    health_timeout_seconds: int = 60,
    extra_env: Mapping[str, str] | None = None,
    repository_url: str | None = None,
    commit: str | None = None,
) -> None:
    logging.getLogger("deploy.workflow").info("deploying %s with %s", settings.name, image_reference)
    env_values = build_updated_environment(settings, image_reference, extra_env)
    if remote:
        prepare_remote_stack(settings, repository_url, commit)
        ensure_remote_bind_mounts(settings)
        push_env_to_remote(settings, env_values)
    else:
        ensure_local_bind_mounts(settings)
        write_env_file(settings.env_file, env_values)
    execute_compose_pull(settings, remote)
    execute_compose_up(settings, remote)
    if not skip_upgrade:
        execute_upgrade(settings, settings.update_modules, remote)
    if skip_health_check:
        return
    run_health_check(settings, remote, health_timeout_seconds)


def show_status(settings: StackSettings, remote: bool) -> None:
    status_command = ["ps"]
    _run_compose(settings, status_command, remote)


def render_settings(settings: StackSettings, image_reference: str) -> str:
    payload = {
        "stack": settings.name,
        "compose_project": settings.compose_project,
        "compose_files": [str(path) for path in settings.compose_files],
        "docker_context": str(settings.docker_context),
        "services": list(settings.services),
        "script_runner_service": settings.script_runner_service,
        "image_variable": settings.image_variable_name,
        "image_reference": image_reference,
        "healthcheck_url": settings.healthcheck_url,
        "remote_host": settings.remote_host,
        "remote_path": str(settings.remote_stack_path) if settings.remote_stack_path is not None else None,
    }
    return json.dumps(payload, indent=2)


def prepare_remote_stack(settings: StackSettings, repository_url: str | None, commit: str | None) -> None:
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote stack configuration incomplete")
    if repository_url is None or commit is None:
        raise ValueError("repository metadata required for remote deployment")
    for file_path in settings.compose_files:
        relative = file_path.relative_to(settings.repo_root)
        target = settings.remote_stack_path / relative
        ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, target.parent)
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, file_path, target)
