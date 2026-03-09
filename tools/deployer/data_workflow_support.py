from __future__ import annotations

import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from .command import run_process
from .compose_ops import local_compose_command, local_compose_env
from .remote import ensure_remote_directory, upload_file
from .settings import StackSettings


def build_updated_environment(
    settings: StackSettings,
    image_reference: str,
    extra_variables: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment_values = settings.environment.copy()
    environment_values[settings.image_variable_name] = image_reference
    if extra_variables is not None:
        environment_values.update(extra_variables)
    return environment_values


def render_env_content(values: Mapping[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    return "\n".join(lines) + "\n"


def write_env_file(path: Path, values: Mapping[str, str]) -> None:
    path.write_text(render_env_content(values), encoding="utf-8")


def ensure_local_bind_mounts(settings: StackSettings) -> None:
    for bind_path in (settings.data_dir, settings.db_dir, settings.log_dir):
        bind_path.mkdir(parents=True, exist_ok=True)
    (settings.log_dir / "sessions").mkdir(parents=True, exist_ok=True)


def push_env_to_remote(settings: StackSettings, env_values: Mapping[str, str]) -> None:
    if settings.remote_host is None:
        raise ValueError("remote host missing")
    if settings.remote_env_path is None:
        raise ValueError("remote env path missing")

    ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, settings.remote_env_path.parent)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temporary_handle:
        temporary_path = Path(temporary_handle.name)
        temporary_handle.write(render_env_content(env_values))
    try:
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, temporary_path, settings.remote_env_path)
        if settings.remote_stack_path is not None:
            default_env_path = settings.remote_stack_path / ".env"
            if default_env_path != settings.remote_env_path:
                ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, default_env_path.parent)
                from .remote import run_remote

                run_remote(
                    settings.remote_host,
                    settings.remote_user,
                    settings.remote_port,
                    ["cp", str(settings.remote_env_path), str(default_env_path)],
                )
    finally:
        temporary_path.unlink(missing_ok=True)


def wait_for_local_service(settings: StackSettings, service: str, *, timeout_seconds: int = 60) -> None:
    if service not in settings.services:
        return
    start_time = time.monotonic()
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
            status_result = run_process(
                ["docker", "inspect", "-f", "{{.State.Status}}", container_id],
                capture_output=True,
                check=False,
            )
            if (status_result.stdout or "").strip() == "running":
                return
        if time.monotonic() - start_time > timeout_seconds:
            raise ValueError(f"Timed out waiting for {service} to be running.")
        time.sleep(2)


def prepare_remote_stack(settings: StackSettings, repository_url: str | None, commit: str | None) -> None:
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote stack configuration incomplete")
    if not repository_url or not commit:
        raise ValueError("repository metadata required for remote deployment")

    for compose_file_path in settings.compose_files:
        relative_path = compose_file_path.relative_to(settings.repo_root)
        remote_target_path = settings.remote_stack_path / relative_path
        ensure_remote_directory(settings.remote_host, settings.remote_user, settings.remote_port, remote_target_path.parent)
        upload_file(settings.remote_host, settings.remote_user, settings.remote_port, compose_file_path, remote_target_path)
