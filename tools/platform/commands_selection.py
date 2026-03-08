from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import click

from . import command_context
from .instance_policies import assert_local_instance_for_local_runtime
from .models import JsonObject, LoadedEnvironment, LoadedStack, RuntimeSelection, StackDefinition


def execute_select(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_with_details_fn: Callable[..., LoadedEnvironment],
    build_runtime_env_values_fn: Callable[..., dict[str, str]],
    parse_env_file_fn: Callable[[Path], dict[str, str]],
    runtime_env_diff_fn: Callable[[dict[str, str], dict[str, str]], JsonObject],
    emit_payload_fn: Callable[..., None],
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_runtime_env_file_fn: Callable[..., Path],
    echo_fn: Callable[[str], None],
    write_pycharm_odoo_conf_fn: Callable[..., Path] | None = None,
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform select")
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = command_context.resolve_stack_file_path(repo_root, stack_file)

    loaded_stack = load_stack_fn(stack_file_path)
    runtime_selection = resolve_runtime_selection_fn(loaded_stack.stack_definition, context_name, instance_name)
    loaded_environment_details = load_environment_with_details_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    loaded_environment = loaded_environment_details.merged_values
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"

    if dry_run:
        runtime_values = build_runtime_env_values_fn(
            runtime_env_file,
            loaded_stack.stack_definition,
            runtime_selection,
            loaded_environment,
        )
        existing_runtime_values = parse_env_file_fn(runtime_env_file) if runtime_env_file.exists() else {}
        payload: JsonObject = {
            "selected_context": context_name,
            "selected_instance": instance_name,
            "dry_run": True,
            "env_file": str(loaded_environment_details.env_file_path),
            "runtime_env_file": str(runtime_env_file),
            "runtime_env_exists": runtime_env_file.exists(),
            "runtime_env_diff": runtime_env_diff_fn(existing_runtime_values, runtime_values),
            "collisions": [
                {
                    "key": collision.key,
                    "previous_layer": collision.previous_layer,
                    "incoming_layer": collision.incoming_layer,
                }
                for collision in loaded_environment_details.collisions
            ],
        }
        emit_payload_fn(payload, json_output=False)
        return

    build_runtime_env_values_fn(
        runtime_env_file,
        loaded_stack.stack_definition,
        runtime_selection,
        loaded_environment,
    )

    write_runtime_odoo_conf_file_fn(runtime_selection, loaded_stack.stack_definition, loaded_environment)
    written_runtime_env_file = write_runtime_env_file_fn(
        repo_root,
        loaded_stack.stack_definition,
        runtime_selection,
        loaded_environment,
    )
    echo_fn(f"selected_context={context_name}")
    echo_fn(f"selected_instance={instance_name}")
    echo_fn(f"runtime_env_file={written_runtime_env_file}")
    if write_pycharm_odoo_conf_fn is not None:
        pycharm_odoo_conf_file = write_pycharm_odoo_conf_fn(
            repo_root=repo_root,
            runtime_selection=runtime_selection,
            stack_definition=loaded_stack.stack_definition,
            source_environment=loaded_environment,
        )
        echo_fn(f"pycharm_odoo_conf_file={pycharm_odoo_conf_file}")

def execute_inspect(
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
    write_runtime_odoo_conf_file_fn: Callable[..., Path],
    write_pycharm_odoo_conf_fn: Callable[..., Path] | None = None,
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform inspect")
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = command_context.resolve_stack_file_path(repo_root, stack_file)

    loaded_stack = load_stack_fn(stack_file_path)
    runtime_selection = resolve_runtime_selection_fn(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_conf_file = write_runtime_odoo_conf_file_fn(runtime_selection, loaded_stack.stack_definition, loaded_environment)
    pycharm_conf_file = None
    if write_pycharm_odoo_conf_fn is not None:
        pycharm_conf_file = write_pycharm_odoo_conf_fn(
            repo_root=repo_root,
            runtime_selection=runtime_selection,
            stack_definition=loaded_stack.stack_definition,
            source_environment=loaded_environment,
        )

    inspection_payload = {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "odoo_conf_host": str(runtime_conf_file),
        "pycharm_odoo_conf_host": str(pycharm_conf_file) if pycharm_conf_file is not None else "",
        "odoo_conf_container": runtime_selection.runtime_odoo_conf_path,
        "addons_path": list(loaded_stack.stack_definition.addons_path),
        "addon_repositories": list(runtime_selection.effective_addon_repositories),
        "install_modules": list(runtime_selection.effective_install_modules),
        "note": "Use pycharm_odoo_conf_host for run configs/tooling with explicit -c config paths; odoo_conf_host is for runtime bootstrap.",
    }

    if json_output:
        click.echo(json.dumps(inspection_payload, indent=2))
        return

    for key, value in inspection_payload.items():
        click.echo(f"{key}={value}")
