from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from . import command_context
from .instance_policies import assert_local_instance_for_local_runtime
from .models import LoadedStack, RuntimeSelection, StackDefinition


def _prepare_runtime_project(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_runtime_env_file_fn: Callable[..., Path],
) -> tuple[command_context.RuntimeCommandContext, Path]:
    runtime_command_context = command_context.load_runtime_command_context(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
    )
    write_runtime_odoo_conf_file_fn(
        runtime_command_context.runtime_selection,
        runtime_command_context.loaded_stack.stack_definition,
        runtime_command_context.environment_values,
    )
    runtime_env_file = write_runtime_env_file_fn(
        discover_repo_root_fn(Path.cwd()),
        runtime_command_context.loaded_stack.stack_definition,
        runtime_command_context.runtime_selection,
        runtime_command_context.environment_values,
    )
    return runtime_command_context, runtime_env_file


def execute_up(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    build_images: bool,
    no_cache: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_runtime_env_file_fn: Callable[..., Path],
    ensure_registry_auth_for_base_images_fn: Callable[[dict[str, str]], None],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform up")
    runtime_command_context, runtime_env_file = _prepare_runtime_project(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
        write_runtime_odoo_conf_file_fn=write_runtime_odoo_conf_file_fn,
        write_runtime_env_file_fn=write_runtime_env_file_fn,
    )
    ensure_registry_auth_for_base_images_fn(runtime_command_context.environment_values)
    compose_command = compose_base_command_fn(runtime_env_file)
    if build_images:
        build_command = compose_command + ["build"]
        if no_cache:
            build_command.append("--no-cache")
        run_command_fn(build_command)
    elif no_cache:
        raise click.ClickException("--no-cache requires --build.")
    run_command_fn(compose_command + ["up", "-d", "--no-build"])
    click.echo(f"up={runtime_command_context.runtime_selection.project_name}")


def _resolve_runtime_env_file(repo_root: Path, context_name: str, instance_name: str) -> Path:
    return repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"


def _require_runtime_env_file(runtime_env_file: Path, *, context_name: str, instance_name: str) -> None:
    if runtime_env_file.exists():
        return
    raise click.ClickException(
        f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
    )


def execute_down(
    *,
    context_name: str,
    instance_name: str,
    volumes: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform down")
    repo_root = discover_repo_root_fn(Path.cwd())
    runtime_env_file = _resolve_runtime_env_file(repo_root, context_name, instance_name)
    _require_runtime_env_file(runtime_env_file, context_name=context_name, instance_name=instance_name)

    down_command = compose_base_command_fn(runtime_env_file) + ["down", "--remove-orphans"]
    if volumes:
        down_command.append("--volumes")
    run_command_fn(down_command)
    click.echo(f"down={context_name}-{instance_name}")


def execute_logs(
    *,
    context_name: str,
    instance_name: str,
    service: str,
    follow: bool,
    lines: int,
    discover_repo_root_fn: Callable[[Path], Path],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform logs")
    repo_root = discover_repo_root_fn(Path.cwd())
    runtime_env_file = _resolve_runtime_env_file(repo_root, context_name, instance_name)
    _require_runtime_env_file(runtime_env_file, context_name=context_name, instance_name=instance_name)

    log_command = compose_base_command_fn(runtime_env_file) + ["logs", "--tail", str(lines)]
    if follow:
        log_command.append("-f")
    log_command.append(service)
    run_command_fn(log_command)


def execute_build(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    no_cache: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_runtime_env_file_fn: Callable[..., Path],
    ensure_registry_auth_for_base_images_fn: Callable[[dict[str, str]], None],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform build")
    runtime_command_context, runtime_env_file = _prepare_runtime_project(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
        write_runtime_odoo_conf_file_fn=write_runtime_odoo_conf_file_fn,
        write_runtime_env_file_fn=write_runtime_env_file_fn,
    )
    ensure_registry_auth_for_base_images_fn(runtime_command_context.environment_values)
    build_command = compose_base_command_fn(runtime_env_file) + ["build"]
    if no_cache:
        build_command.append("--no-cache")
    run_command_fn(build_command)
    click.echo(f"build={runtime_command_context.runtime_selection.project_name}")


def execute_odoo_shell(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    script_path: Path,
    service: str,
    database_name: str | None,
    log_file: Path | None,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_runtime_env_file_fn: Callable[..., Path],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_with_input_fn: Callable[[list[str], str], None],
    run_command_with_input_to_log_fn: Callable[[list[str], str, Path], None],
    echo_fn: Callable[[str], None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform odoo-shell")
    repo_root = discover_repo_root_fn(Path.cwd())
    resolved_script_path = script_path if script_path.is_absolute() else (repo_root / script_path)
    if not resolved_script_path.exists() or not resolved_script_path.is_file():
        raise click.ClickException(f"Script file not found: {resolved_script_path}")

    runtime_command_context, runtime_env_file = _prepare_runtime_project(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
        write_runtime_odoo_conf_file_fn=write_runtime_odoo_conf_file_fn,
        write_runtime_env_file_fn=write_runtime_env_file_fn,
    )

    selected_database_name = database_name or runtime_command_context.runtime_selection.database_name
    addons_path_argument = ",".join(runtime_command_context.loaded_stack.stack_definition.addons_path)
    odoo_shell_command = [
        "/odoo/odoo-bin",
        "shell",
        "-d",
        selected_database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={runtime_command_context.environment_values.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={runtime_command_context.environment_values.get('ODOO_DB_PASSWORD', '')}",
    ]
    compose_command = compose_base_command_fn(runtime_env_file) + ["exec", "-T", service] + odoo_shell_command
    resolved_log_file = None
    if log_file is not None:
        resolved_log_file = log_file if log_file.is_absolute() else (repo_root / log_file)

    echo_fn(f"odoo_shell_service={service}")
    echo_fn(f"odoo_shell_database={selected_database_name}")
    echo_fn(f"odoo_shell_script={resolved_script_path}")
    if dry_run:
        if resolved_log_file is not None:
            echo_fn(f"odoo_shell_log_file={resolved_log_file}")
        echo_fn(f"odoo_shell_command={' '.join(compose_command)}")
        return

    script_contents = resolved_script_path.read_text(encoding="utf-8")
    if resolved_log_file is not None:
        run_command_with_input_to_log_fn(compose_command, script_contents, resolved_log_file)
        echo_fn(f"odoo_shell_log_file={resolved_log_file}")
        return
    run_command_with_input_fn(compose_command, script_contents)
