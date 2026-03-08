from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import click

from . import command_context
from .models import JsonObject, LoadedStack, RuntimeSelection, StackDefinition


def _base_runtime_payload(runtime_selection: RuntimeSelection) -> JsonObject:
    return {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "project_name": runtime_selection.project_name,
        "state_path": str(runtime_selection.state_path),
        "runtime_conf_host_path": str(runtime_selection.runtime_conf_host_path),
        "data_volume": runtime_selection.data_volume_name,
        "log_volume": runtime_selection.log_volume_name,
        "db_volume": runtime_selection.db_volume_name,
        "web_host_port": runtime_selection.web_host_port,
        "longpoll_host_port": runtime_selection.longpoll_host_port,
        "db_host_port": runtime_selection.db_host_port,
        "install_modules": list(runtime_selection.effective_install_modules),
        "addon_repositories": list(runtime_selection.effective_addon_repositories),
    }


def execute_validate_config(
    *,
    stack_file: Path,
    env_file: Path | None,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = command_context.resolve_stack_file_path(repo_root, stack_file)
    loaded_stack = load_stack_fn(stack_file_path)
    env_file_path, parsed_environment = load_environment_fn(repo_root, env_file)

    missing_required_keys = [
        required_key
        for required_key in loaded_stack.stack_definition.required_env_keys
        if not parsed_environment.get(required_key)
    ]

    click.echo(f"stack_file={loaded_stack.stack_file_path}")
    click.echo(f"env_file={env_file_path}")
    click.echo(f"schema_version={loaded_stack.stack_definition.schema_version}")
    click.echo(f"contexts={','.join(sorted(loaded_stack.stack_definition.contexts))}")

    if missing_required_keys:
        raise click.ClickException(f"Missing required env keys: {', '.join(missing_required_keys)}")

    click.echo("validation=ok")


def execute_list_contexts(
    *,
    stack_file: Path,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = command_context.resolve_stack_file_path(repo_root, stack_file)
    loaded_stack = load_stack_fn(stack_file_path)
    context_names = sorted(loaded_stack.stack_definition.contexts)

    if json_output:
        click.echo(json.dumps({"contexts": context_names}, indent=2))
        return

    for context_name in context_names:
        click.echo(context_name)


def execute_render_odoo_conf(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    output_file: Path,
    include_comments: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    render_odoo_config_fn: Callable[..., str],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = command_context.resolve_stack_file_path(repo_root, stack_file)

    _env_file_path, environment_values = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    loaded_stack = load_stack_fn(stack_file_path)
    rendered_configuration = render_odoo_config_fn(
        stack_definition=loaded_stack.stack_definition,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        include_comments=include_comments,
    )

    output_file_path = output_file if output_file.is_absolute() else (repo_root / output_file)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(rendered_configuration, encoding="utf-8")
    click.echo(f"wrote={output_file_path}")


def execute_doctor(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    local_runtime_status_fn: Callable[[Path], JsonObject],
    dokploy_status_payload_fn: Callable[..., JsonObject],
    emit_payload_fn: Callable[..., None],
) -> None:
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

    payload: JsonObject = {
        **_base_runtime_payload(runtime_command_context.runtime_selection),
        "root_env_file": str(runtime_command_context.env_file_path),
        "runtime_env_file": str(runtime_command_context.runtime_env_file),
        "local_runtime": local_runtime_status_fn(runtime_command_context.runtime_env_file),
        "dokploy": dokploy_status_payload_fn(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=runtime_command_context.environment_values,
        ),
    }
    emit_payload_fn(payload, json_output=json_output)


def execute_info(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    dokploy_status_payload_fn: Callable[..., JsonObject],
    emit_payload_fn: Callable[..., None],
) -> None:
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

    missing_required_env_keys = [
        required_key
        for required_key in runtime_command_context.loaded_stack.stack_definition.required_env_keys
        if not runtime_command_context.environment_values.get(required_key, "").strip()
    ]

    payload: JsonObject = {
        **_base_runtime_payload(runtime_command_context.runtime_selection),
        "runtime_env_file": str(runtime_command_context.runtime_env_file),
        "runtime_env_exists": runtime_command_context.runtime_env_file.exists(),
        "root_env_file": str(runtime_command_context.env_file_path),
        "required_env_keys": list(runtime_command_context.loaded_stack.stack_definition.required_env_keys),
        "missing_required_env_keys": missing_required_env_keys,
        "dokploy": dokploy_status_payload_fn(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=runtime_command_context.environment_values,
        ),
    }
    emit_payload_fn(payload, json_output=json_output)


def execute_status(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    local_runtime_status_fn: Callable[[Path], JsonObject],
    dokploy_status_payload_fn: Callable[..., JsonObject],
    emit_payload_fn: Callable[..., None],
) -> None:
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

    payload: JsonObject = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "context": runtime_command_context.runtime_selection.context_name,
        "instance": runtime_command_context.runtime_selection.instance_name,
        "project_name": runtime_command_context.runtime_selection.project_name,
        "local": local_runtime_status_fn(runtime_command_context.runtime_env_file),
        "dokploy": dokploy_status_payload_fn(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=runtime_command_context.environment_values,
        ),
    }
    emit_payload_fn(payload, json_output=json_output)
