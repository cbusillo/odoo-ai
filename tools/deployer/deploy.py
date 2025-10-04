import json
import logging
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .compose_ops import local_compose, remote_compose_command
from .health import HealthcheckError, wait_for_health
from .remote import ensure_remote_directory, run_remote, sync_remote_repository, upload_file
from .settings import StackSettings


def build_updated_environment(
    settings: StackSettings, image_reference: str, extra_variables: Mapping[str, str] | None = None
) -> dict[str, str]:
    data = dict(settings.environment)
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


def ensure_remote_bind_mounts(settings: StackSettings) -> None:
    if settings.remote_host is None:
        return
    for path in (settings.data_dir, settings.db_dir, settings.log_dir):
        ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, path)


def push_env_to_remote(settings: StackSettings, env_values: Mapping[str, str]) -> None:
    if settings.remote_host is None:
        raise ValueError("remote host missing")
    if settings.remote_env_path is None:
        raise ValueError("remote env path missing")
    ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, settings.remote_env_path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(render_env_content(env_values))
    try:
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, temp_path, settings.remote_env_path)
    finally:
        temp_path.unlink(missing_ok=True)


def execute_compose_pull(settings: StackSettings, remote: bool) -> None:
    if remote:
        if settings.remote_host is None:
            raise ValueError("remote host missing")
        if settings.remote_stack_path is None:
            raise ValueError("remote stack path missing")
        command = remote_compose_command(settings, ["pull", *settings.services])
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        local_compose(settings, ["pull", *settings.services])


def execute_compose_up(settings: StackSettings, remote: bool) -> None:
    if remote:
        if settings.remote_host is None:
            raise ValueError("remote host missing")
        if settings.remote_stack_path is None:
            raise ValueError("remote stack path missing")
        command = remote_compose_command(settings, ["up", "-d", *settings.services])
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        local_compose(settings, ["up", "-d", *settings.services])


def execute_upgrade(settings: StackSettings, modules: tuple[str, ...], remote: bool) -> None:
    if not modules:
        raise ValueError("no modules configured for upgrade")
    module_argument = ",".join(dict.fromkeys(modules))
    upgrade_subcommand = [
        "exec",
        "-T",
        settings.script_runner_service,
        "bash",
        "-lc",
        f"{settings.odoo_bin_path} -u {module_argument} -d $ODOO_DB_NAME --stop-after-init",
    ]
    if remote:
        if settings.remote_host is None:
            raise ValueError("remote host missing")
        if settings.remote_stack_path is None:
            raise ValueError("remote stack path missing")
        command = remote_compose_command(settings, upgrade_subcommand)
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        local_compose(settings, upgrade_subcommand)


def run_health_check(settings: StackSettings, remote: bool, timeout_seconds: int) -> None:
    if remote and settings.remote_host is not None:
        command = ["curl", "-sf", settings.healthcheck_url]
        try:
            run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command)
            return
        except Exception as error:  # noqa: BLE001
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
    if remote:
        if settings.remote_host is None:
            raise ValueError("remote host missing")
        if settings.remote_stack_path is None:
            raise ValueError("remote stack path missing")
        command = remote_compose_command(settings, status_command)
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        local_compose(settings, status_command)


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
    sync_remote_repository(
        settings.remote_host,
        settings.remote_user,
        settings.remote_port,
        settings.remote_stack_path,
        repository_url,
        commit,
        settings.github_token,
    )
    for file_path in settings.compose_files:
        relative = file_path.relative_to(settings.repo_root)
        target = settings.remote_stack_path / relative
        ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, target.parent)
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, file_path, target)
