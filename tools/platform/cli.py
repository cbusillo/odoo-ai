from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import click

from tools.platform import commands_core as platform_commands_core
from tools.platform import commands_dokploy as platform_commands_dokploy
from tools.platform import commands_lifecycle as platform_commands_lifecycle
from tools.platform import commands_release as platform_commands_release
from tools.platform import commands_selection as platform_commands_selection
from tools.platform import commands_workflow as platform_commands_workflow
from tools.platform import dokploy as platform_dokploy
from tools.platform import environment as platform_environment
from tools.platform import ide_support as platform_ide_support
from tools.platform import registry as platform_registry
from tools.platform import release_workflows as platform_release_workflows
from tools.platform import runtime as platform_runtime
from tools.platform import runtime_status as platform_runtime_status
from tools.platform import workflow_runtime as platform_workflow_runtime
from tools.platform.models import (
    ContextDefinition,
    DokploySourceOfTruth,
    DokployTargetDefinition,
    EnvironmentCollision,
    JsonObject,
    JsonValue,
    LoadedEnvironment,
    LoadedStack,
    RuntimeSelection,
    ShipBranchSyncPlan,
    StackDefinition,
)
from tools.stack_data_workflow import run_stack_data_workflow
from tools.validate import shopify_roundtrip as validate_shopify_roundtrip

PLATFORM_RUNTIME_ENV_KEYS = (
    "PLATFORM_CONTEXT",
    "PLATFORM_INSTANCE",
    "PLATFORM_RUNTIME_ENV_FILE",
    "PYTHON_VERSION",
    "ODOO_VERSION",
    "ODOO_STACK_NAME",
    "ODOO_PROJECT_NAME",
    "ODOO_STATE_ROOT",
    "ODOO_RUNTIME_CONF_HOST_PATH",
    "DOCKER_IMAGE",
    "DOCKER_IMAGE_TAG",
    "COMPOSE_BUILD_TARGET",
    "ODOO_DATA_VOLUME",
    "ODOO_LOG_VOLUME",
    "ODOO_DB_VOLUME",
    "ODOO_DB_NAME",
    "ODOO_DB_USER",
    "ODOO_DB_PASSWORD",
    "ODOO_FILESTORE_PATH",
    "ODOO_MASTER_PASSWORD",
    "ODOO_ADMIN_LOGIN",
    "ODOO_INSTALL_MODULES",
    "ODOO_ADDON_REPOSITORIES",
    "ODOO_UPDATE_MODULES",
    "ODOO_ADDONS_PATH",
    "ODOO_WEB_HOST_PORT",
    "ODOO_LONGPOLL_HOST_PORT",
    "ODOO_DB_HOST_PORT",
    "ODOO_LIST_DB",
    "ODOO_WEB_COMMAND",
    "ODOO_DATA_WORKFLOW_LOCK_FILE",
    "ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS",
    "ODOO_DB_MAXCONN",
    "ODOO_DB_MAXCONN_GEVENT",
    "ODOO_WORKERS",
    "ODOO_MAX_CRON_THREADS",
    "ODOO_LIMIT_TIME_CPU",
    "ODOO_LIMIT_TIME_REAL",
    "ODOO_LIMIT_TIME_REAL_CRON",
    "ODOO_LIMIT_TIME_WORKER_CRON",
    "ODOO_LIMIT_MEMORY_SOFT",
    "ODOO_LIMIT_MEMORY_HARD",
    "ODOO_DEV_MODE",
    "ODOO_LOGFILE",
    "POSTGRES_MAX_CONNECTIONS",
    "POSTGRES_SHARED_BUFFERS",
    "POSTGRES_EFFECTIVE_CACHE_SIZE",
    "POSTGRES_WORK_MEM",
    "POSTGRES_MAINTENANCE_WORK_MEM",
    "POSTGRES_MAX_WAL_SIZE",
    "POSTGRES_MIN_WAL_SIZE",
    "POSTGRES_CHECKPOINT_TIMEOUT",
    "POSTGRES_RANDOM_PAGE_COST",
    "POSTGRES_EFFECTIVE_IO_CONCURRENCY",
    "DATA_WORKFLOW_SSH_DIR",
    "DATA_WORKFLOW_SSH_KEY",
    "ODOO_UPSTREAM_HOST",
    "ODOO_UPSTREAM_USER",
    "ODOO_UPSTREAM_DB_NAME",
    "ODOO_UPSTREAM_DB_USER",
    "ODOO_UPSTREAM_FILESTORE_PATH",
    "OPENUPGRADE_ENABLED",
    "OPENUPGRADE_ADDON_REPOSITORY",
    "OPENUPGRADE_SCRIPTS_PATH",
    "OPENUPGRADE_TARGET_VERSION",
    "OPENUPGRADE_SKIP_UPDATE_ADDONS",
    "OPENUPGRADELIB_INSTALL_SPEC",
    "GITHUB_TOKEN",
    "DOKPLOY_HOST",
    "DOKPLOY_TOKEN",
)

PLATFORM_RUNTIME_PASSTHROUGH_PREFIXES = (
    "ENV_OVERRIDE_",
    "ODOO_UPSTREAM_",
)

PLATFORM_RUNTIME_PASSTHROUGH_KEYS = (
    "ODOO_KEY",
    "DATA_WORKFLOW_SSH_KEY",
    "DOKPLOY_HOST",
    "DOKPLOY_TOKEN",
)

ENV_COLLISION_MODE_ENV_KEY = platform_environment.ENV_COLLISION_MODE_ENV_KEY
VALID_ENV_COLLISION_MODES = platform_environment.VALID_ENV_COLLISION_MODES

PLATFORM_RUN_WORKFLOWS = (
    "restore",
    "bootstrap",
    "init",
    "update",
    "openupgrade",
)

PLATFORM_TUI_WORKFLOWS = (
    "select",
    "info",
    "status",
    "up",
    "build",
    "ship",
    *PLATFORM_RUN_WORKFLOWS,
)

DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF = "origin/main"


def _discover_repo_root(start_directory: Path) -> Path:
    return platform_environment.discover_repo_root(start_directory)


def _parse_env_file(env_file_path: Path) -> dict[str, str]:
    return platform_environment.parse_env_file(env_file_path)


def _resolve_platform_secrets_file(repo_root: Path) -> Path:
    return platform_environment.resolve_platform_secrets_file(repo_root)


def _resolve_env_collision_mode(collision_mode: str | None) -> str:
    return platform_environment.resolve_env_collision_mode(collision_mode)


def _handle_environment_collisions(collisions: tuple[EnvironmentCollision, ...], collision_mode: str) -> None:
    platform_environment.handle_environment_collisions(collisions, collision_mode)


def _load_environment_with_details(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> LoadedEnvironment:
    return platform_environment.load_environment_with_details(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode=collision_mode,
    )


def _load_environment(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> tuple[Path, dict[str, str]]:
    return platform_environment.load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode=collision_mode,
    )


def _load_stack(stack_file_path: Path) -> LoadedStack:
    return platform_environment.load_stack(stack_file_path)


def _load_dokploy_source_of_truth(source_file_path: Path) -> DokploySourceOfTruth:
    return platform_environment.load_dokploy_source_of_truth(source_file_path)


def _resolve_runtime_selection(stack_definition: StackDefinition, context_name: str, instance_name: str) -> RuntimeSelection:
    try:
        return platform_runtime.resolve_runtime_selection(
            stack_definition,
            context_name,
            instance_name,
            _discover_repo_root,
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error


def _write_runtime_odoo_conf_file(
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    return platform_runtime.write_runtime_odoo_conf_file(
        runtime_selection,
        stack_definition,
        source_environment,
    )


def _build_runtime_env_values(
    runtime_env_file: Path,
    stack_definition: StackDefinition,
    runtime_selection: RuntimeSelection,
    source_environment: dict[str, str],
) -> dict[str, str]:
    openupgrade_environment = dict(source_environment)
    for runtime_key, runtime_value in runtime_selection.effective_runtime_env.items():
        openupgrade_environment[runtime_key] = str(runtime_value)

    effective_addon_repositories = platform_runtime.effective_runtime_addon_repositories(
        runtime_selection=runtime_selection,
        source_environment=openupgrade_environment,
    )

    runtime_values = {
        "PLATFORM_CONTEXT": runtime_selection.context_name,
        "PLATFORM_INSTANCE": runtime_selection.instance_name,
        "PLATFORM_RUNTIME_ENV_FILE": str(runtime_env_file),
        "PYTHON_VERSION": source_environment.get("PYTHON_VERSION", "3.13"),
        "ODOO_VERSION": stack_definition.odoo_version,
        "ODOO_STACK_NAME": f"{runtime_selection.context_name}-{runtime_selection.instance_name}",
        "ODOO_PROJECT_NAME": runtime_selection.project_name,
        "ODOO_STATE_ROOT": str(runtime_selection.state_path),
        "ODOO_RUNTIME_CONF_HOST_PATH": str(runtime_selection.runtime_conf_host_path),
        "DOCKER_IMAGE": source_environment.get("DOCKER_IMAGE", runtime_selection.project_name),
        "DOCKER_IMAGE_TAG": source_environment.get("DOCKER_IMAGE_TAG", "latest"),
        "COMPOSE_BUILD_TARGET": source_environment.get("COMPOSE_BUILD_TARGET", "development"),
        "ODOO_DATA_VOLUME": runtime_selection.data_volume_name,
        "ODOO_LOG_VOLUME": runtime_selection.log_volume_name,
        "ODOO_DB_VOLUME": runtime_selection.db_volume_name,
        "ODOO_DB_NAME": runtime_selection.database_name,
        "ODOO_DB_USER": source_environment.get("ODOO_DB_USER", "odoo"),
        "ODOO_DB_PASSWORD": source_environment.get("ODOO_DB_PASSWORD", ""),
        "ODOO_FILESTORE_PATH": source_environment.get("ODOO_FILESTORE_PATH", "/volumes/data/filestore"),
        "ODOO_MASTER_PASSWORD": source_environment.get("ODOO_MASTER_PASSWORD", ""),
        "ODOO_ADMIN_LOGIN": source_environment.get("ODOO_ADMIN_LOGIN", ""),
        "ODOO_ADMIN_PASSWORD": source_environment.get("ODOO_ADMIN_PASSWORD", ""),
        "ODOO_INSTALL_MODULES": ",".join(runtime_selection.effective_install_modules),
        "ODOO_ADDON_REPOSITORIES": ",".join(effective_addon_repositories),
        "ODOO_UPDATE_MODULES": runtime_selection.context_definition.update_modules,
        "ODOO_ADDONS_PATH": ",".join(stack_definition.addons_path),
        "ODOO_WEB_HOST_PORT": str(runtime_selection.web_host_port),
        "ODOO_LONGPOLL_HOST_PORT": str(runtime_selection.longpoll_host_port),
        "ODOO_DB_HOST_PORT": str(runtime_selection.db_host_port),
        "ODOO_LIST_DB": "False",
        "ODOO_WEB_COMMAND": f"python3 /volumes/scripts/run_odoo_startup.py -c {runtime_selection.runtime_odoo_conf_path}",
        "ODOO_DATA_WORKFLOW_LOCK_FILE": source_environment.get(
            "ODOO_DATA_WORKFLOW_LOCK_FILE", "/volumes/data/.data_workflow_in_progress"
        ),
        "ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS": source_environment.get("ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS", "7200"),
        "DATA_WORKFLOW_SSH_DIR": source_environment.get(
            "DATA_WORKFLOW_SSH_DIR",
            str(Path.home() / ".ssh") if runtime_selection.instance_name == "local" else "/home/ubuntu/.ssh",
        ),
        "OPENUPGRADE_ENABLED": openupgrade_environment.get("OPENUPGRADE_ENABLED", "False"),
        "OPENUPGRADE_ADDON_REPOSITORY": openupgrade_environment.get("OPENUPGRADE_ADDON_REPOSITORY", ""),
        "OPENUPGRADE_SCRIPTS_PATH": openupgrade_environment.get("OPENUPGRADE_SCRIPTS_PATH", ""),
        "OPENUPGRADE_TARGET_VERSION": openupgrade_environment.get("OPENUPGRADE_TARGET_VERSION", ""),
        "OPENUPGRADE_SKIP_UPDATE_ADDONS": openupgrade_environment.get("OPENUPGRADE_SKIP_UPDATE_ADDONS", "True"),
        "OPENUPGRADELIB_INSTALL_SPEC": openupgrade_environment.get("OPENUPGRADELIB_INSTALL_SPEC", ""),
        "ODOO_PYTHON_SYNC_SKIP_ADDONS": source_environment.get("ODOO_PYTHON_SYNC_SKIP_ADDONS", ""),
        "GITHUB_TOKEN": source_environment.get("GITHUB_TOKEN", ""),
    }

    if platform_runtime.openupgrade_enabled(openupgrade_environment):
        runtime_values["OPENUPGRADE_ADDON_REPOSITORY"] = platform_runtime.resolve_openupgrade_addon_repository(
            openupgrade_environment
        )
        runtime_values["OPENUPGRADELIB_INSTALL_SPEC"] = platform_runtime.resolve_openupgradelib_install_spec(openupgrade_environment)
        runtime_values["ODOO_PYTHON_SYNC_SKIP_ADDONS"] = "openupgrade_framework,openupgrade_scripts,openupgrade_scripts_custom"

    for environment_key in sorted(source_environment):
        include_value = environment_key in PLATFORM_RUNTIME_PASSTHROUGH_KEYS or any(
            environment_key.startswith(prefix) for prefix in PLATFORM_RUNTIME_PASSTHROUGH_PREFIXES
        )
        if not include_value:
            continue
        runtime_values[environment_key] = source_environment[environment_key]

    for runtime_key, runtime_value in runtime_selection.effective_runtime_env.items():
        runtime_values[runtime_key] = runtime_value

    return runtime_values


def _render_runtime_env(runtime_values: dict[str, str]) -> str:
    return platform_runtime.render_runtime_env(runtime_values)


def _runtime_env_diff(existing_values: dict[str, str], proposed_values: dict[str, str]) -> JsonObject:
    return platform_runtime.runtime_env_diff(existing_values, proposed_values)


def _write_runtime_env_file(
    repo_root: Path,
    stack_definition: StackDefinition,
    runtime_selection: RuntimeSelection,
    source_environment: dict[str, str],
) -> Path:
    runtime_env_directory = repo_root / ".platform" / "env"
    runtime_env_directory.mkdir(parents=True, exist_ok=True)
    runtime_env_file = runtime_env_directory / f"{runtime_selection.context_name}.{runtime_selection.instance_name}.env"

    runtime_selection.runtime_conf_host_path.parent.mkdir(parents=True, exist_ok=True)

    runtime_values = _build_runtime_env_values(
        runtime_env_file,
        stack_definition,
        runtime_selection,
        source_environment,
    )
    runtime_env_file.write_text(_render_runtime_env(runtime_values), encoding="utf-8")
    return runtime_env_file


def _write_pycharm_odoo_conf(
    *,
    repo_root: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    return platform_ide_support.write_pycharm_odoo_conf(
        repo_root=repo_root,
        runtime_selection=runtime_selection,
        stack_definition=stack_definition,
        source_environment=source_environment,
    )


def _compose_base_command(runtime_env_file: Path) -> list[str]:
    repo_root = _discover_repo_root(Path.cwd())
    compose_files = [
        repo_root / "docker-compose.yml",
        repo_root / "platform" / "compose" / "base.yaml",
    ]
    optional_override_file = repo_root / "docker-compose.override.yml"
    if optional_override_file.exists():
        compose_files.append(optional_override_file)

    missing_files = [compose_file for compose_file in compose_files if not compose_file.exists()]
    if missing_files:
        missing_display = ", ".join(str(compose_file) for compose_file in missing_files)
        raise click.ClickException(f"Missing required compose files: {missing_display}")

    command = [
        "docker",
        "compose",
        "--project-directory",
        str(repo_root),
        "--env-file",
        str(runtime_env_file),
    ]
    for compose_file in compose_files:
        command.extend(["-f", str(compose_file)])

    return command


def _ensure_registry_auth_for_base_images(environment_values: dict[str, str]) -> None:
    platform_registry.ensure_registry_auth_for_base_images(environment_values)


def _run_command(command: list[str]) -> None:
    result = subprocess.run(command, env=_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}")


def _run_command_best_effort(command: list[str]) -> int:
    result = subprocess.run(command, env=_command_execution_env())
    return result.returncode


def _run_command_with_input(command: list[str], input_text: str) -> None:
    result = subprocess.run(command, input=input_text.encode(), env=_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}")


def _run_command_with_input_to_log(command: list[str], input_text: str, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("wb") as log_handle:
        result = subprocess.run(
            command,
            input=input_text.encode(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=_command_execution_env(),
        )
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}\nLog file: {log_file}")


def _run_command_capture(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, env=_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        stderr_text = result.stderr.strip()
        message = f"Command failed ({result.returncode}): {joined_command}"
        if stderr_text:
            message = f"{message}\n{stderr_text}"
        raise click.ClickException(message)
    return result.stdout


def _command_execution_env() -> dict[str, str]:
    execution_env = dict(os.environ)
    for runtime_key in PLATFORM_RUNTIME_ENV_KEYS:
        execution_env.pop(runtime_key, None)
    for passthrough_key in PLATFORM_RUNTIME_PASSTHROUGH_KEYS:
        execution_env.pop(passthrough_key, None)
    for environment_key in list(execution_env):
        if any(environment_key.startswith(prefix) for prefix in PLATFORM_RUNTIME_PASSTHROUGH_PREFIXES):
            execution_env.pop(environment_key, None)
    return execution_env


def _resolve_local_git_commit(git_reference: str) -> str:
    raw_output = _run_command_capture(["git", "rev-parse", "--verify", f"{git_reference}^{{commit}}"])
    return raw_output.strip()


def _collect_dirty_tracked_files() -> tuple[str, ...]:
    raw_status_output = _run_command_capture(["git", "status", "--short", "--no-untracked-files"])
    dirty_lines: list[str] = []
    for raw_line in raw_status_output.splitlines():
        cleaned_line = raw_line.strip()
        if cleaned_line:
            dirty_lines.append(cleaned_line)
    return tuple(dirty_lines)


def _resolve_remote_git_branch_commit(remote_name: str, branch_name: str) -> str:
    raw_output = _run_command_capture(["git", "ls-remote", "--heads", remote_name, f"refs/heads/{branch_name}"])
    for raw_line in raw_output.splitlines():
        cleaned_line = raw_line.strip()
        if not cleaned_line:
            continue
        split_line = cleaned_line.split()
        if split_line:
            return split_line[0].strip()
    return ""


def _resolve_ship_source_git_ref(
    source_git_ref_override: str,
    target_definition: DokployTargetDefinition | None,
) -> str:
    cleaned_override = source_git_ref_override.strip()
    if cleaned_override:
        return cleaned_override
    if target_definition is not None:
        cleaned_target_reference = target_definition.source_git_ref.strip()
        if cleaned_target_reference:
            return cleaned_target_reference
    return DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF


def _prepare_ship_branch_sync(
    source_git_ref_override: str,
    target_definition: DokployTargetDefinition | None,
) -> ShipBranchSyncPlan | None:
    if target_definition is None:
        return None
    target_branch = target_definition.git_branch.strip()
    if not target_branch:
        return None

    _run_command(["git", "fetch", "origin", "--prune"])
    source_git_ref = _resolve_ship_source_git_ref(source_git_ref_override, target_definition)
    source_commit = _resolve_local_git_commit(source_git_ref)
    remote_branch_commit_before = _resolve_remote_git_branch_commit("origin", target_branch)
    branch_update_required = source_commit != remote_branch_commit_before
    return ShipBranchSyncPlan(
        source_git_ref=source_git_ref,
        source_commit=source_commit,
        target_branch=target_branch,
        remote_branch_commit_before=remote_branch_commit_before,
        branch_update_required=branch_update_required,
    )


def _apply_ship_branch_sync(ship_branch_sync_plan: ShipBranchSyncPlan) -> None:
    if not ship_branch_sync_plan.branch_update_required:
        return
    _run_command(
        [
            "git",
            "push",
            "origin",
            f"+{ship_branch_sync_plan.source_commit}:refs/heads/{ship_branch_sync_plan.target_branch}",
        ]
    )


def _local_runtime_status(runtime_env_file: Path) -> JsonObject:
    return platform_runtime_status.local_runtime_status(
        runtime_env_file,
        compose_base_command_fn=_compose_base_command,
        run_command_capture_fn=_run_command_capture,
    )


def _resolve_dokploy_target(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    ship_mode: str,
    target_definition: DokployTargetDefinition | None = None,
) -> tuple[str, str, str, click.ClickException | None, click.ClickException | None]:
    return platform_dokploy.resolve_dokploy_target(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        ship_mode=ship_mode,
        target_definition=target_definition,
    )


def _summarize_deployment(deployment: JsonObject | None) -> JsonObject | None:
    return platform_dokploy.summarize_deployment(deployment)


def _dokploy_status_payload(
    *,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> JsonObject:
    repo_root = _discover_repo_root(Path.cwd())
    source_of_truth = _load_dokploy_source_of_truth_if_present(repo_root)
    target_definition: DokployTargetDefinition | None = None
    if source_of_truth is not None:
        target_definition = _find_dokploy_target_definition(
            source_of_truth,
            context_name=context_name,
            instance_name=instance_name,
        )

    return platform_dokploy.dokploy_status_payload(
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        target_definition=target_definition,
    )


def _emit_payload(payload: JsonObject, *, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            click.echo(f"{key}={json.dumps(value)}")
            continue
        click.echo(f"{key}={value}")


def _resolve_dokploy_target_for_command(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    target_type: str,
    target_definition: DokployTargetDefinition | None = None,
) -> tuple[str, str, str]:
    return platform_dokploy.resolve_dokploy_target_for_command(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        target_type=target_type,
        target_definition=target_definition,
    )


def _parse_dokploy_env_text(raw_env_text: str) -> dict[str, str]:
    return platform_dokploy.parse_dokploy_env_text(raw_env_text)


def _serialize_dokploy_env_text(env_map: dict[str, str]) -> str:
    return platform_dokploy.serialize_dokploy_env_text(env_map)


def _fetch_dokploy_target_payload(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
) -> JsonObject:
    return platform_dokploy.fetch_dokploy_target_payload(
        host=host,
        token=token,
        target_type=target_type,
        target_id=target_id,
    )


def _update_dokploy_target_env(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
    target_payload: JsonObject,
    env_text: str,
) -> None:
    platform_dokploy.update_dokploy_target_env(
        host=host,
        token=token,
        target_type=target_type,
        target_id=target_id,
        target_payload=target_payload,
        env_text=env_text,
    )


def _resolve_dokploy_runtime(
    *,
    repo_root: Path,
    env_file: Path | None,
    context_name: str,
    instance_name: str,
    target_type: str,
) -> tuple[str, str, str, str, str, dict[str, str]]:
    source_of_truth = _load_dokploy_source_of_truth_if_present(repo_root)
    target_definition: DokployTargetDefinition | None = None
    if source_of_truth is not None:
        target_definition = _find_dokploy_target_definition(
            source_of_truth,
            context_name=context_name,
            instance_name=instance_name,
        )

    _env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    host, token = _read_dokploy_config(environment_values)
    resolved_target_type, resolved_target_id, resolved_target_name = _resolve_dokploy_target_for_command(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        target_type=target_type,
        target_definition=target_definition,
    )
    return host, token, resolved_target_type, resolved_target_id, resolved_target_name, environment_values


def _resolve_dokploy_source_file(repo_root: Path, source_file: Path | None) -> Path:
    return platform_dokploy.resolve_dokploy_source_file(repo_root, source_file)


def _load_dokploy_source_of_truth_if_present(repo_root: Path) -> DokploySourceOfTruth | None:
    return platform_dokploy.load_dokploy_source_of_truth_if_present(repo_root, _load_dokploy_source_of_truth)


def _find_dokploy_target_definition(
    source_of_truth: DokploySourceOfTruth,
    *,
    context_name: str,
    instance_name: str,
) -> DokployTargetDefinition | None:
    return platform_dokploy.find_dokploy_target_definition(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )


def _run_gate_command(command: list[str], *, dry_run: bool) -> None:
    platform_release_workflows.run_gate_command(command, dry_run=dry_run, run_command=_run_command)


def _run_code_gate(*, context_name: str, dry_run: bool) -> None:
    _run_gate_command(
        ["env", "TESTKIT_PROFILE=gate", "uv", "run", "test", "run", "--json", "--stack", context_name],
        dry_run=dry_run,
    )


def _run_production_backup_gate(*, context_name: str, dry_run: bool) -> None:
    _run_gate_command(["uv", "run", "prod-gate", "backup", "--target", context_name], dry_run=dry_run)


def _assert_prod_data_workflow_allowed(*, instance_name: str, workflow: str, allow_prod_data_workflow: bool) -> None:
    platform_release_workflows.assert_prod_data_workflow_allowed(
        instance_name=instance_name,
        workflow=workflow,
        allow_prod_data_workflow=allow_prod_data_workflow,
    )


def _collect_environment_gate_results(*, urls: tuple[str, ...], timeout_seconds: int) -> list[JsonObject]:
    return platform_release_workflows.collect_environment_gate_results(
        urls=urls,
        timeout_seconds=timeout_seconds,
        wait_for_ship_healthcheck=lambda url, timeout: _wait_for_ship_healthcheck(url=url, timeout_seconds=timeout),
    )


def _assert_promote_path_allowed(*, from_instance_name: str, to_instance_name: str) -> None:
    platform_release_workflows.assert_promote_path_allowed(
        from_instance_name=from_instance_name,
        to_instance_name=to_instance_name,
    )


def _validate_target_gate_policy(*, target_definition: DokployTargetDefinition) -> None:
    platform_release_workflows.validate_target_gate_policy(target_definition=target_definition)


def _run_required_gates(
    *,
    context_name: str,
    target_definition: DokployTargetDefinition | None,
    dry_run: bool,
    skip_gate: bool,
) -> None:
    platform_release_workflows.run_required_gates(
        context_name=context_name,
        target_definition=target_definition,
        dry_run=dry_run,
        skip_gate=skip_gate,
        validate_target_gate_policy_fn=_validate_target_gate_policy,
        run_code_gate_fn=_run_code_gate,
        run_production_backup_gate_fn=_run_production_backup_gate,
        echo_fn=click.echo,
    )


def _target_matches_filters(
    target: DokployTargetDefinition,
    *,
    context_filter: str | None,
    instance_filter: str | None,
) -> bool:
    if context_filter and target.context != context_filter:
        return False
    if instance_filter and target.instance != instance_filter:
        return False
    return True


def _normalize_domains(raw_domains: object) -> list[str]:
    if not isinstance(raw_domains, list):
        return []
    normalized_domains: list[str] = []
    for domain_item in raw_domains:
        domain_payload = platform_dokploy.as_json_object(domain_item)
        if domain_payload is None:
            continue
        host = str(domain_payload.get("host") or "").strip()
        if host and host not in normalized_domains:
            normalized_domains.append(host)
    return normalized_domains


def _run_init_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
) -> None:
    platform_workflow_runtime.run_init_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
        run_command_best_effort_fn=_run_command_best_effort,
        run_command_with_input_fn=_run_command_with_input,
        echo_fn=click.echo,
    )


def _run_update_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
) -> None:
    platform_workflow_runtime.run_update_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
        run_command_best_effort_fn=_run_command_best_effort,
        echo_fn=click.echo,
    )


def _run_openupgrade_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
) -> None:
    platform_workflow_runtime.run_openupgrade_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
        run_command_best_effort_fn=_run_command_best_effort,
        echo_fn=click.echo,
    )


def _ordered_instance_names(context_definition: ContextDefinition) -> list[str]:
    return platform_workflow_runtime.ordered_instance_names(context_definition)


def _run_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
    echo_fn: Callable[[str], None] = click.echo,
) -> None:
    platform_workflow_runtime.run_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
        allow_prod_data_workflow=allow_prod_data_workflow,
        assert_prod_data_workflow_allowed_fn=_assert_prod_data_workflow_allowed,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_runtime_env_file_fn=_write_runtime_env_file,
        run_stack_data_workflow_fn=run_stack_data_workflow,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
        run_command_best_effort_fn=_run_command_best_effort,
        run_command_with_input_fn=_run_command_with_input,
        invoke_platform_command_fn=_invoke_platform_command,
        echo_fn=echo_fn,
    )


def _run_tui_ship_workflow(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    no_cache: bool,
    allow_dirty: bool,
    echo_fn: Callable[[str], None] = click.echo,
) -> None:
    platform_commands_release.execute_ship(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        wait=True,
        timeout_override_seconds=None,
        verify_health=True,
        health_timeout_override_seconds=None,
        dry_run=dry_run,
        no_cache=no_cache,
        skip_gate=False,
        allow_dirty=allow_dirty,
        source_git_ref="",
        discover_repo_root_fn=_discover_repo_root,
        load_environment_fn=_load_environment,
        load_dokploy_source_of_truth_if_present_fn=_load_dokploy_source_of_truth_if_present,
        find_dokploy_target_definition_fn=_find_dokploy_target_definition,
        resolve_ship_timeout_seconds_fn=_resolve_ship_timeout_seconds,
        resolve_ship_health_timeout_seconds_fn=_resolve_ship_health_timeout_seconds,
        resolve_ship_healthcheck_urls_fn=_resolve_ship_healthcheck_urls,
        prepare_ship_branch_sync_fn=_prepare_ship_branch_sync,
        run_required_gates_fn=_run_required_gates,
        resolve_dokploy_ship_mode_fn=_resolve_dokploy_ship_mode,
        read_dokploy_config_fn=_read_dokploy_config,
        resolve_dokploy_target_fn=_resolve_dokploy_target,
        apply_ship_branch_sync_fn=_apply_ship_branch_sync,
        dokploy_request_fn=_dokploy_request,
        latest_deployment_for_compose_fn=_latest_deployment_for_compose,
        deployment_key_fn=_deployment_key,
        wait_for_dokploy_compose_deployment_fn=_wait_for_dokploy_compose_deployment,
        verify_ship_healthchecks_fn=_verify_ship_healthchecks,
        latest_deployment_for_application_fn=_latest_deployment_for_application,
        wait_for_dokploy_deployment_fn=_wait_for_dokploy_deployment,
        echo_fn=echo_fn,
        check_dirty_working_tree_fn=_collect_dirty_tracked_files,
    )


def _invoke_platform_command(command_name: str, **kwargs: object) -> None:
    command = main.commands.get(command_name)
    if command is None:
        raise click.ClickException(f"Platform command '{command_name}' is not registered.")
    callback = command.callback
    if callback is None or not callable(callback):
        raise click.ClickException(f"Platform command '{command_name}' has no callable callback.")
    callback(**kwargs)


def _dokploy_request(
    *,
    host: str,
    token: str,
    path: str,
    method: str = "GET",
    payload: JsonObject | None = None,
    query: dict[str, str | int | float] | None = None,
) -> JsonObject:
    response_payload = platform_dokploy.dokploy_request(
        host=host,
        token=token,
        path=path,
        method=method,
        payload=payload,
        query=query,
    )
    response_object = platform_dokploy.as_json_object(response_payload)
    if response_object is not None:
        return response_object
    if isinstance(response_payload, list):
        # Some deployment endpoints return a top-level list. Wrap it so
        # downstream helpers can parse consistently via extract_deployments().
        return {"data": response_payload}
    if isinstance(response_payload, (str, int, float, bool)) or response_payload is None:
        raise click.ClickException(
            f"Dokploy endpoint {path} returned an unsupported scalar payload: {type(response_payload).__name__}."
        )
    raise click.ClickException(f"Dokploy endpoint {path} returned a non-object payload.")


def _read_dokploy_config(environment_values: dict[str, str]) -> tuple[str, str]:
    return platform_dokploy.read_dokploy_config(environment_values)


def _extract_deployments(raw_payload: JsonValue) -> list[JsonObject]:
    return platform_dokploy.extract_deployments(raw_payload)


def _deployment_key(deployment: JsonObject) -> str:
    return platform_dokploy.deployment_key(deployment)


def _resolve_dokploy_ship_mode(
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> str:
    return platform_dokploy.resolve_dokploy_ship_mode(context_name, instance_name, environment_values)


def _latest_deployment_for_application(host: str, token: str, application_id: str) -> JsonObject | None:
    return platform_dokploy.latest_deployment_for_application(host, token, application_id)


def _latest_deployment_for_compose(host: str, token: str, compose_id: str) -> JsonObject | None:
    return platform_dokploy.latest_deployment_for_compose(host, token, compose_id)


def _collect_rollback_ids(payload: JsonValue | list[JsonObject]) -> list[str]:
    return platform_dokploy.collect_rollback_ids(payload)


def _wait_for_dokploy_deployment(
    *,
    host: str,
    token: str,
    application_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    return platform_dokploy.wait_for_dokploy_deployment(
        host=host,
        token=token,
        application_id=application_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )


def _wait_for_dokploy_compose_deployment(
    *,
    host: str,
    token: str,
    compose_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    return platform_dokploy.wait_for_dokploy_compose_deployment(
        host=host,
        token=token,
        compose_id=compose_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )


def _resolve_ship_timeout_seconds(
    *,
    timeout_override_seconds: int | None,
    target_definition: DokployTargetDefinition | None,
) -> int:
    return platform_dokploy.resolve_ship_timeout_seconds(
        timeout_override_seconds=timeout_override_seconds,
        target_definition=target_definition,
    )


def _resolve_ship_health_timeout_seconds(
    *,
    health_timeout_override_seconds: int | None,
    target_definition: DokployTargetDefinition | None,
) -> int:
    return platform_dokploy.resolve_ship_health_timeout_seconds(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )


def _resolve_ship_healthcheck_urls(
    *,
    target_definition: DokployTargetDefinition | None,
    environment_values: dict[str, str],
) -> tuple[str, ...]:
    return platform_dokploy.resolve_ship_healthcheck_urls(
        target_definition=target_definition,
        environment_values=environment_values,
    )


def _wait_for_ship_healthcheck(*, url: str, timeout_seconds: int) -> str:
    return platform_dokploy.wait_for_ship_healthcheck(url=url, timeout_seconds=timeout_seconds)


def _verify_ship_healthchecks(*, urls: tuple[str, ...], timeout_seconds: int) -> None:
    platform_dokploy.verify_ship_healthchecks(urls=urls, timeout_seconds=timeout_seconds)


def _render_odoo_config(
    *,
    stack_definition: StackDefinition,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    include_comments: bool,
) -> str:
    runtime_selection = _resolve_runtime_selection(stack_definition, context_name, instance_name)

    lines: list[str] = [
        "[options]",
        f"db_name = {runtime_selection.database_name}",
        f"db_user = {environment_values.get('ODOO_DB_USER', 'odoo')}",
        f"db_password = {environment_values.get('ODOO_DB_PASSWORD', '')}",
        "db_host = database",
        "db_port = 5432",
        "list_db = False",
        f"addons_path = {','.join(stack_definition.addons_path)}",
        f"data_dir = {runtime_selection.data_mount}",
    ]

    if include_comments:
        lines.append("")
        lines.append(f"; context={context_name}")
        lines.append(f"; instance={instance_name}")
        lines.append(f"; install_modules={','.join(runtime_selection.effective_install_modules)}")
        lines.append(f"; update_modules={runtime_selection.context_definition.update_modules}")

    return "\n".join(lines) + "\n"


LOCAL_RUNTIME_CONTRACT_HELP = (
    "Local host runtime only. Requires --instance local. "
    "Remote dev/testing/prod instances use ship/rollback/gate/promote, plus separate restore and bootstrap data workflows."
)
REMOTE_RUNTIME_CONTRACT_HELP = (
    "Dokploy-managed remote workflow for dev/testing/prod. "
    "Use ship for non-destructive deploy/restart. Restore and bootstrap are explicit data workflows; init/update remain local-only."
)
DESTRUCTIVE_DATA_WORKFLOW_HELP = (
    "Destructive data workflow. Supports local runtime plus remote dev/testing/prod targets. "
    "Use --allow-prod-data-workflow only for explicit prod break-glass operations."
)


@click.group(
    help=(
        "Platform operator CLI. Local runtime mutations use --instance local; "
        "Dokploy-managed remote targets use ship/rollback/gate/promote, plus separate restore and bootstrap data workflows."
    )
)
def main() -> None:
    return None


@main.command("validate-config")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
def validate_config(stack_file: Path, env_file: Path | None) -> None:
    platform_commands_core.execute_validate_config(
        stack_file=stack_file,
        env_file=env_file,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        load_environment_fn=_load_environment,
    )


@main.group("validate", help="Run tracked environment validation scenarios against a selected instance.")
def validate() -> None:
    return None


@validate.command("shopify-roundtrip", help="Run the Shopify round-trip validation scenario against a managed target.")
@click.option("--context", "context_name", default="opw", show_default=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(validate_shopify_roundtrip.SUPPORTED_REMOTE_INSTANCES, case_sensitive=False),
    default="testing",
    show_default=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--remote-login", default=validate_shopify_roundtrip.DEFAULT_REMOTE_LOGIN, show_default=True)
def validate_shopify_roundtrip_command(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
) -> None:
    results = validate_shopify_roundtrip.run_validation_command(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        remote_login=remote_login,
        repository_root=_discover_repo_root(Path.cwd()),
    )
    click.echo(json.dumps(results, indent=2, sort_keys=True))


@main.command("list-contexts")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--json-output", is_flag=True, default=False)
def list_contexts(stack_file: Path, json_output: bool) -> None:
    platform_commands_core.execute_list_contexts(
        stack_file=stack_file,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
    )


@main.group("secrets")
def secrets_group() -> None:
    return None


@secrets_group.command("explain")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--collision-mode",
    type=click.Choice(VALID_ENV_COLLISION_MODES, case_sensitive=False),
    default="warn",
    show_default=True,
)
@click.option("--show-values", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def secrets_explain(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    collision_mode: str,
    show_values: bool,
    json_output: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    loaded_environment = _load_environment_with_details(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode="ignore",
    )
    normalized_collision_mode = _resolve_env_collision_mode(collision_mode)
    _handle_environment_collisions(loaded_environment.collisions, normalized_collision_mode)

    rendered_keys: list[JsonValue] = []
    keys_by_source: dict[str, JsonValue] = {}
    for environment_key in sorted(loaded_environment.merged_values):
        source_layer = loaded_environment.source_by_key.get(environment_key, "")
        existing_source_keys = keys_by_source.get(source_layer)
        if isinstance(existing_source_keys, list):
            existing_source_keys.append(environment_key)
        else:
            keys_by_source[source_layer] = [environment_key]
        rendered_key: JsonObject = {
            "key": environment_key,
            "source": source_layer,
            "value": loaded_environment.merged_values[environment_key] if show_values else "<redacted>",
        }
        rendered_keys.append(rendered_key)

    rendered_collisions: list[JsonValue] = []
    for collision in loaded_environment.collisions:
        rendered_collisions.append(
            {
                "key": collision.key,
                "previous_layer": collision.previous_layer,
                "incoming_layer": collision.incoming_layer,
            }
        )

    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "env_file": str(loaded_environment.env_file_path),
        "secrets_file": str(_resolve_platform_secrets_file(repo_root)),
        "secrets_file_exists": _resolve_platform_secrets_file(repo_root).exists(),
        "collision_mode": normalized_collision_mode,
        "collision_count": len(loaded_environment.collisions),
        "collisions": rendered_collisions,
        "merged_key_count": len(loaded_environment.merged_values),
        "keys_by_source": keys_by_source,
        "keys": rendered_keys,
    }
    _emit_payload(payload, json_output=json_output)


@main.command("render-odoo-conf")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    default=Path(".platform/odoo.conf"),
    show_default=True,
)
@click.option("--include-comments/--no-comments", default=True)
def render_odoo_conf(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    output_file: Path,
    include_comments: bool,
) -> None:
    platform_commands_core.execute_render_odoo_conf(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        output_file=output_file,
        include_comments=include_comments,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        load_environment_fn=_load_environment,
        render_odoo_config_fn=_render_odoo_config,
    )


@main.command(
    "doctor",
    help=(
        "Inspect the selected platform target without mutating it. "
        "Reports local runtime status for --instance local and Dokploy target status for remote instances."
    ),
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def doctor(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None, json_output: bool) -> None:
    platform_commands_core.execute_doctor(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        local_runtime_status_fn=_local_runtime_status,
        dokploy_status_payload_fn=_dokploy_status_payload,
        emit_payload_fn=_emit_payload,
    )


@main.command("info")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def info(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
) -> None:
    platform_commands_core.execute_info(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        dokploy_status_payload_fn=_dokploy_status_payload,
        emit_payload_fn=_emit_payload,
    )


@main.command("status")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def status(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
) -> None:
    platform_commands_core.execute_status(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        local_runtime_status_fn=_local_runtime_status,
        dokploy_status_payload_fn=_dokploy_status_payload,
        emit_payload_fn=_emit_payload,
    )


@main.command(
    "gate",
    help=(
        "Run release checks for a selected target. "
        "Use this for Dokploy-managed remote instances before client validation or promotion."
    ),
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--phase",
    type=click.Choice(("code", "env", "all"), case_sensitive=False),
    default="all",
    show_default=True,
)
@click.option(
    "--health-timeout",
    "health_timeout_override_seconds",
    type=int,
    default=None,
    help="Environment health-check timeout in seconds per endpoint.",
)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def gate(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    phase: str,
    health_timeout_override_seconds: int | None,
    dry_run: bool,
    json_output: bool,
) -> None:
    platform_release_workflows.execute_gate(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        phase=phase,
        health_timeout_override_seconds=health_timeout_override_seconds,
        dry_run=dry_run,
        json_output=json_output,
        run_code_gate_fn=_run_code_gate,
        discover_repo_root_fn=_discover_repo_root,
        load_environment_fn=_load_environment,
        load_dokploy_source_of_truth_if_present_fn=_load_dokploy_source_of_truth_if_present,
        find_dokploy_target_definition_fn=_find_dokploy_target_definition,
        resolve_ship_health_timeout_seconds_fn=_resolve_ship_health_timeout_seconds,
        resolve_ship_healthcheck_urls_fn=_resolve_ship_healthcheck_urls,
        dokploy_status_payload_fn=_dokploy_status_payload,
        collect_environment_gate_results_fn=_collect_environment_gate_results,
        emit_payload_fn=_emit_payload,
    )


@main.command(
    "run",
    help=(
        "Run platform workflows such as restore, bootstrap, init, update, or openupgrade. "
        "Restore and bootstrap support remote targets; init/update/openupgrade remain local-only."
    ),
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--workflow", required=True, type=click.Choice(PLATFORM_RUN_WORKFLOWS, case_sensitive=False))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-cache", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.option("--reset-versions", is_flag=True, default=False)
@click.option(
    "--allow-prod-data-workflow",
    is_flag=True,
    default=False,
    help="Allow destructive restore or bootstrap workflows on prod instances (break-glass only).",
)
def run_workflow(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
) -> None:
    platform_commands_workflow.execute_run_workflow_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
        allow_prod_data_workflow=allow_prod_data_workflow,
        run_workflow_fn=_run_workflow,
    )


@main.command(
    "tui",
    help=(
        "Interactive platform workflow launcher. "
        "Supports wildcard fan-out for read-only workflows (status/info) via context or instance all/* selectors. "
        "Mutating workflows, including ship, require explicit single-target selection."
    ),
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option(
    "--context",
    "context_name",
    default=None,
    help="Context selector (single or comma-separated). Use all or * for read-only fan-out.",
)
@click.option(
    "--instance",
    "instance_name",
    default=None,
    help="Instance selector (single or comma-separated). Use all or * for read-only fan-out.",
)
@click.option(
    "--workflow",
    default=None,
    type=click.Choice(PLATFORM_TUI_WORKFLOWS, case_sensitive=False),
    help="Workflow to run. Wildcard fan-out allows only status/info.",
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-cache", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.option("--reset-versions", is_flag=True, default=False)
@click.option(
    "--json",
    "--json-output",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit machine-readable JSON summary for fan-out runs.",
)
@click.option(
    "--allow-prod-data-workflow",
    is_flag=True,
    default=False,
    help="Allow destructive restore or bootstrap workflows on prod instances (break-glass only).",
)
def tui(
    stack_file: Path,
    context_name: str | None,
    instance_name: str | None,
    workflow: str | None,
    env_file: Path | None,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    json_output: bool,
    allow_prod_data_workflow: bool,
) -> None:
    platform_commands_workflow.execute_tui_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        workflow=workflow,
        env_file=env_file,
        dry_run=dry_run,
        no_cache=no_cache,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
        json_output=json_output,
        allow_prod_data_workflow=allow_prod_data_workflow,
        platform_tui_workflows=PLATFORM_TUI_WORKFLOWS,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        ordered_instance_names_fn=_ordered_instance_names,
        run_workflow_fn=_run_workflow,
        run_ship_fn=_run_tui_ship_workflow,
        check_dirty_working_tree_fn=_collect_dirty_tracked_files,
    )


def _parse_env_assignment(assignment: str) -> tuple[str, str]:
    if "=" not in assignment:
        raise click.ClickException(f"Invalid --set value '{assignment}'. Expected KEY=VALUE.")
    key_part, value_part = assignment.split("=", 1)
    env_key = key_part.strip()
    if not env_key:
        raise click.ClickException(f"Invalid --set value '{assignment}'. Empty key is not allowed.")
    return env_key, value_part


@main.group("dokploy")
def dokploy_group() -> None:
    return None


@dokploy_group.command("env-get")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--target-type",
    default="auto",
    show_default=True,
    type=click.Choice(("auto", "compose", "application"), case_sensitive=False),
)
@click.option("--key", "keys", multiple=True)
@click.option("--prefix", "prefixes", multiple=True)
@click.option("--show-values", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_env_get(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    keys: tuple[str, ...],
    prefixes: tuple[str, ...],
    show_values: bool,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_env_get(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        keys=keys,
        prefixes=prefixes,
        show_values=show_values,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        resolve_dokploy_runtime_fn=_resolve_dokploy_runtime,
        fetch_dokploy_target_payload_fn=_fetch_dokploy_target_payload,
        parse_dokploy_env_text_fn=_parse_dokploy_env_text,
        emit_payload_fn=_emit_payload,
    )


@dokploy_group.command("env-set")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--target-type",
    default="auto",
    show_default=True,
    type=click.Choice(("auto", "compose", "application"), case_sensitive=False),
)
@click.option("--set", "assignments", multiple=True, required=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_env_set(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    assignments: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_env_set(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        assignments=assignments,
        dry_run=dry_run,
        json_output=json_output,
        parse_env_assignment_fn=_parse_env_assignment,
        discover_repo_root_fn=_discover_repo_root,
        resolve_dokploy_runtime_fn=_resolve_dokploy_runtime,
        fetch_dokploy_target_payload_fn=_fetch_dokploy_target_payload,
        parse_dokploy_env_text_fn=_parse_dokploy_env_text,
        update_dokploy_target_env_fn=_update_dokploy_target_env,
        serialize_dokploy_env_text_fn=_serialize_dokploy_env_text,
        emit_payload_fn=_emit_payload,
    )


@dokploy_group.command("env-unset")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--target-type",
    default="auto",
    show_default=True,
    type=click.Choice(("auto", "compose", "application"), case_sensitive=False),
)
@click.option("--key", "keys", multiple=True)
@click.option("--prefix", "prefixes", multiple=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_env_unset(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    keys: tuple[str, ...],
    prefixes: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_env_unset(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        keys=keys,
        prefixes=prefixes,
        dry_run=dry_run,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        resolve_dokploy_runtime_fn=_resolve_dokploy_runtime,
        fetch_dokploy_target_payload_fn=_fetch_dokploy_target_payload,
        parse_dokploy_env_text_fn=_parse_dokploy_env_text,
        update_dokploy_target_env_fn=_update_dokploy_target_env,
        serialize_dokploy_env_text_fn=_serialize_dokploy_env_text,
        emit_payload_fn=_emit_payload,
    )


@dokploy_group.command("logs")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--target-type",
    default="auto",
    show_default=True,
    type=click.Choice(("auto", "compose", "application"), case_sensitive=False),
)
@click.option("--limit", default=5, show_default=True)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_logs(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    limit: int,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_logs(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        limit=limit,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        resolve_dokploy_runtime_fn=_resolve_dokploy_runtime,
        dokploy_request_fn=_dokploy_request,
        extract_deployments_fn=_extract_deployments,
        summarize_deployment_fn=_summarize_deployment,
        emit_payload_fn=_emit_payload,
    )


@dokploy_group.command("inventory")
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--output-file", type=click.Path(path_type=Path), default=None)
@click.option("--snapshot-dir", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_inventory(
    env_file: Path | None,
    output_file: Path | None,
    snapshot_dir: Path | None,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_inventory(
        env_file=env_file,
        output_file=output_file,
        snapshot_dir=snapshot_dir,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_environment_fn=_load_environment,
        read_dokploy_config_fn=_read_dokploy_config,
        dokploy_request_fn=_dokploy_request,
        fetch_dokploy_target_payload_fn=_fetch_dokploy_target_payload,
        emit_payload_fn=_emit_payload,
    )


@dokploy_group.command("reconcile")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option(
    "--source-file",
    type=click.Path(path_type=Path),
    default=Path("platform/dokploy.toml"),
    show_default=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--context", "context_filter", default=None)
@click.option("--instance", "instance_filter", default=None)
@click.option("--apply", is_flag=True, default=False)
@click.option(
    "--prune-env",
    is_flag=True,
    default=False,
    help="Remove reconcile-managed remote env keys (ENV_OVERRIDE_* and ODOO_WEB_COMMAND) that are absent from source.",
)
@click.option("--json-output", is_flag=True, default=False)
def dokploy_reconcile(
    stack_file: Path,
    source_file: Path,
    env_file: Path | None,
    context_filter: str | None,
    instance_filter: str | None,
    apply: bool,
    prune_env: bool,
    json_output: bool,
) -> None:
    platform_commands_dokploy.execute_reconcile(
        stack_file=stack_file,
        source_file=source_file,
        env_file=env_file,
        context_filter=context_filter,
        instance_filter=instance_filter,
        apply=apply,
        prune_env=prune_env,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_dokploy_source_file_fn=_resolve_dokploy_source_file,
        load_dokploy_source_of_truth_fn=_load_dokploy_source_of_truth,
        load_environment_fn=_load_environment,
        read_dokploy_config_fn=_read_dokploy_config,
        target_matches_filters_fn=_target_matches_filters,
        fetch_dokploy_target_payload_fn=_fetch_dokploy_target_payload,
        normalize_domains_fn=_normalize_domains,
        dokploy_request_fn=_dokploy_request,
        update_dokploy_target_env_fn=_update_dokploy_target_env,
        parse_dokploy_env_text_fn=_parse_dokploy_env_text,
        serialize_dokploy_env_text_fn=_serialize_dokploy_env_text,
        emit_payload_fn=_emit_payload,
    )


@main.command("select", help=f"Render and select local runtime artifacts. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
def select(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
) -> None:
    platform_commands_selection.execute_select(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_with_details_fn=_load_environment_with_details,
        build_runtime_env_values_fn=_build_runtime_env_values,
        parse_env_file_fn=_parse_env_file,
        runtime_env_diff_fn=_runtime_env_diff,
        emit_payload_fn=_emit_payload,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_runtime_env_file_fn=_write_runtime_env_file,
        write_pycharm_odoo_conf_fn=_write_pycharm_odoo_conf,
        echo_fn=click.echo,
    )


@main.command("up", help=f"Start the local compose runtime. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--build/--no-build", "build_images", default=True)
@click.option("--no-cache", is_flag=True, default=False)
def up(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    build_images: bool,
    no_cache: bool,
) -> None:
    platform_commands_lifecycle.execute_up(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        build_images=build_images,
        no_cache=no_cache,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_runtime_env_file_fn=_write_runtime_env_file,
        ensure_registry_auth_for_base_images_fn=_ensure_registry_auth_for_base_images,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
    )


@main.command("down", help=f"Stop the local compose runtime. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--volumes", is_flag=True, default=False)
def down(context_name: str, instance_name: str, volumes: bool) -> None:
    platform_commands_lifecycle.execute_down(
        context_name=context_name,
        instance_name=instance_name,
        volumes=volumes,
        discover_repo_root_fn=_discover_repo_root,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
    )


@main.command("logs", help=f"Read logs from the local compose runtime. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--service", default="web", show_default=True)
@click.option("--follow/--no-follow", default=True)
@click.option("--lines", default=200, show_default=True)
def logs(context_name: str, instance_name: str, service: str, follow: bool, lines: int) -> None:
    platform_commands_lifecycle.execute_logs(
        context_name=context_name,
        instance_name=instance_name,
        service=service,
        follow=follow,
        lines=lines,
        discover_repo_root_fn=_discover_repo_root,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
    )


def _run_with_web_temporarily_stopped(
    runtime_env_file: Path,
    operation: Callable[[], None],
    *,
    dry_run: bool,
    dry_run_commands: tuple[list[str], ...],
) -> None:
    platform_workflow_runtime.run_with_web_temporarily_stopped(
        runtime_env_file,
        operation,
        dry_run=dry_run,
        dry_run_commands=dry_run_commands,
        compose_base_command_fn=_compose_base_command,
        run_command_best_effort_fn=_run_command_best_effort,
        echo_fn=click.echo,
    )


@main.command("build", help=f"Build local compose images. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--no-cache", is_flag=True, default=False)
def build(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    no_cache: bool,
) -> None:
    platform_commands_lifecycle.execute_build(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        no_cache=no_cache,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_runtime_env_file_fn=_write_runtime_env_file,
        ensure_registry_auth_for_base_images_fn=_ensure_registry_auth_for_base_images,
        compose_base_command_fn=_compose_base_command,
        run_command_fn=_run_command,
    )


@main.command("odoo-shell", help=f"Run an Odoo shell script against the local runtime. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--script", "script_path", type=click.Path(path_type=Path), required=True)
@click.option("--service", default="script-runner", show_default=True)
@click.option("--database", "database_name", default=None)
@click.option("--log-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
def odoo_shell(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    script_path: Path,
    service: str,
    database_name: str | None,
    log_file: Path | None,
    dry_run: bool,
) -> None:
    platform_commands_lifecycle.execute_odoo_shell(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        script_path=script_path,
        service=service,
        database_name=database_name,
        log_file=log_file,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_runtime_env_file_fn=_write_runtime_env_file,
        compose_base_command_fn=_compose_base_command,
        run_command_with_input_fn=_run_command_with_input,
        run_command_with_input_to_log_fn=_run_command_with_input_to_log,
        echo_fn=click.echo,
    )


@main.command("inspect", help=f"Inspect rendered local runtime configuration. {LOCAL_RUNTIME_CONTRACT_HELP}")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def inspect_context(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
) -> None:
    platform_commands_selection.execute_inspect(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        json_output=json_output,
        discover_repo_root_fn=_discover_repo_root,
        load_stack_fn=_load_stack,
        resolve_runtime_selection_fn=_resolve_runtime_selection,
        load_environment_fn=_load_environment,
        write_runtime_odoo_conf_file_fn=_write_runtime_odoo_conf_file,
        write_pycharm_odoo_conf_fn=_write_pycharm_odoo_conf,
    )


@main.command(
    "promote",
    help=f"Promote the exact tested commit from testing to prod for a Dokploy-managed target. {REMOTE_RUNTIME_CONTRACT_HELP}",
)
@click.option("--context", "context_name", required=True)
@click.option(
    "--from-instance",
    "from_instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    default="testing",
    show_default=True,
)
@click.option(
    "--to-instance",
    "to_instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    required=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--wait/--no-wait", default=True)
@click.option(
    "--timeout",
    "timeout_override_seconds",
    type=int,
    default=None,
    help="Deployment wait timeout in seconds. Defaults to platform/dokploy.toml per-target value or 600.",
)
@click.option(
    "--verify-health/--no-verify-health",
    default=True,
    help="Verify /web/health endpoints for the promoted target after deploy.",
)
@click.option(
    "--health-timeout",
    "health_timeout_override_seconds",
    type=int,
    default=None,
    help="Health verification timeout in seconds per endpoint for the promoted target.",
)
@click.option(
    "--verify-source-health/--no-verify-source-health",
    default=True,
    help="Require source instance health checks before promotion.",
)
@click.option(
    "--source-health-timeout",
    "source_health_timeout_override_seconds",
    type=int,
    default=None,
    help="Health verification timeout in seconds per endpoint for the source instance.",
)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-cache", is_flag=True, default=False, help="Request rebuild deployment on Dokploy target.")
def promote(
    context_name: str,
    from_instance_name: str,
    to_instance_name: str,
    env_file: Path | None,
    wait: bool,
    timeout_override_seconds: int | None,
    verify_health: bool,
    health_timeout_override_seconds: int | None,
    verify_source_health: bool,
    source_health_timeout_override_seconds: int | None,
    dry_run: bool,
    no_cache: bool,
) -> None:
    platform_release_workflows.execute_promote(
        context_name=context_name,
        from_instance_name=from_instance_name,
        to_instance_name=to_instance_name,
        env_file=env_file,
        wait=wait,
        timeout_override_seconds=timeout_override_seconds,
        verify_health=verify_health,
        health_timeout_override_seconds=health_timeout_override_seconds,
        verify_source_health=verify_source_health,
        source_health_timeout_override_seconds=source_health_timeout_override_seconds,
        dry_run=dry_run,
        no_cache=no_cache,
        assert_promote_path_allowed_fn=_assert_promote_path_allowed,
        discover_repo_root_fn=_discover_repo_root,
        load_dokploy_source_of_truth_if_present_fn=_load_dokploy_source_of_truth_if_present,
        find_dokploy_target_definition_fn=_find_dokploy_target_definition,
        run_command_fn=_run_command,
        resolve_remote_git_branch_commit_fn=_resolve_remote_git_branch_commit,
        load_environment_fn=_load_environment,
        resolve_ship_health_timeout_seconds_fn=_resolve_ship_health_timeout_seconds,
        resolve_ship_healthcheck_urls_fn=_resolve_ship_healthcheck_urls,
        collect_environment_gate_results_fn=_collect_environment_gate_results,
        run_production_backup_gate_fn=_run_production_backup_gate,
        invoke_platform_command_fn=_invoke_platform_command,
        echo_fn=click.echo,
    )


@main.command(
    "ship",
    help=f"Deploy an exact git ref to a Dokploy-managed remote target. {REMOTE_RUNTIME_CONTRACT_HELP}",
)
@click.option("--context", "context_name", required=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    required=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--wait/--no-wait", default=True)
@click.option(
    "--timeout",
    "timeout_override_seconds",
    type=int,
    default=None,
    help="Deployment wait timeout in seconds. Defaults to platform/dokploy.toml per-target value or 600.",
)
@click.option(
    "--verify-health/--no-verify-health",
    default=True,
    help="Verify /web/health endpoints after a successful deploy when --wait is enabled.",
)
@click.option(
    "--health-timeout",
    "health_timeout_override_seconds",
    type=int,
    default=None,
    help="Health verification timeout in seconds per endpoint. Defaults to per-target value or 180.",
)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-cache", is_flag=True, default=False, help="Request rebuild deployment on Dokploy target.")
@click.option("--skip-gate", is_flag=True, default=False, help="Skip required test/prod gates from platform/dokploy.toml.")
@click.option(
    "--allow-dirty",
    is_flag=True,
    default=False,
    help="Allow ship from a dirty tracked working tree (uncommitted changes). Prefer a clean worktree plus --source-ref for surgical tests.",
)
@click.option(
    "--source-ref",
    "source_git_ref",
    default="",
    help="Git reference used to sync the Dokploy target branch before deploy. Use this to test an exact commit or worktree HEAD. Defaults to target source_git_ref or origin/main.",
)
def ship(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    wait: bool,
    timeout_override_seconds: int | None,
    verify_health: bool,
    health_timeout_override_seconds: int | None,
    dry_run: bool,
    no_cache: bool,
    skip_gate: bool,
    allow_dirty: bool,
    source_git_ref: str,
) -> None:
    platform_commands_release.execute_ship(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        wait=wait,
        timeout_override_seconds=timeout_override_seconds,
        verify_health=verify_health,
        health_timeout_override_seconds=health_timeout_override_seconds,
        dry_run=dry_run,
        no_cache=no_cache,
        skip_gate=skip_gate,
        allow_dirty=allow_dirty,
        source_git_ref=source_git_ref,
        discover_repo_root_fn=_discover_repo_root,
        load_environment_fn=_load_environment,
        load_dokploy_source_of_truth_if_present_fn=_load_dokploy_source_of_truth_if_present,
        find_dokploy_target_definition_fn=_find_dokploy_target_definition,
        resolve_ship_timeout_seconds_fn=_resolve_ship_timeout_seconds,
        resolve_ship_health_timeout_seconds_fn=_resolve_ship_health_timeout_seconds,
        resolve_ship_healthcheck_urls_fn=_resolve_ship_healthcheck_urls,
        prepare_ship_branch_sync_fn=_prepare_ship_branch_sync,
        run_required_gates_fn=_run_required_gates,
        resolve_dokploy_ship_mode_fn=_resolve_dokploy_ship_mode,
        read_dokploy_config_fn=_read_dokploy_config,
        resolve_dokploy_target_fn=_resolve_dokploy_target,
        apply_ship_branch_sync_fn=_apply_ship_branch_sync,
        dokploy_request_fn=_dokploy_request,
        latest_deployment_for_compose_fn=_latest_deployment_for_compose,
        deployment_key_fn=_deployment_key,
        wait_for_dokploy_compose_deployment_fn=_wait_for_dokploy_compose_deployment,
        verify_ship_healthchecks_fn=_verify_ship_healthchecks,
        latest_deployment_for_application_fn=_latest_deployment_for_application,
        wait_for_dokploy_deployment_fn=_wait_for_dokploy_deployment,
        echo_fn=click.echo,
        check_dirty_working_tree_fn=_collect_dirty_tracked_files,
    )


@main.command(
    "rollback",
    help=(
        "List or trigger Dokploy rollback targets for a remote deployment. "
        "Rollback currently supports Dokploy application targets only; compose targets must use Dokploy UI rollback controls. "
        f"{REMOTE_RUNTIME_CONTRACT_HELP}"
    ),
)
@click.option("--context", "context_name", required=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    required=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--rollback-id", default="", help="Explicit Dokploy rollback id")
@click.option("--list", "list_only", is_flag=True, default=False, help="List discovered rollback ids and exit")
@click.option("--wait/--no-wait", default=True)
@click.option("--timeout", "timeout_seconds", default=600, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def rollback(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    rollback_id: str,
    list_only: bool,
    wait: bool,
    timeout_seconds: int,
    dry_run: bool,
) -> None:
    platform_commands_release.execute_rollback(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        rollback_id=rollback_id,
        list_only=list_only,
        wait=wait,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        discover_repo_root_fn=_discover_repo_root,
        load_environment_fn=_load_environment,
        load_dokploy_source_of_truth_if_present_fn=_load_dokploy_source_of_truth_if_present,
        find_dokploy_target_definition_fn=_find_dokploy_target_definition,
        resolve_dokploy_ship_mode_fn=_resolve_dokploy_ship_mode,
        read_dokploy_config_fn=_read_dokploy_config,
        dokploy_request_fn=_dokploy_request,
        extract_deployments_fn=_extract_deployments,
        collect_rollback_ids_fn=_collect_rollback_ids,
        latest_deployment_for_application_fn=_latest_deployment_for_application,
        deployment_key_fn=_deployment_key,
        wait_for_dokploy_deployment_fn=_wait_for_dokploy_deployment,
        echo_fn=click.echo,
    )


@main.command(
    "restore",
    help=f"Restore database and filestore state from the configured upstream source. {DESTRUCTIVE_DATA_WORKFLOW_HELP}",
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option(
    "--allow-prod-data-workflow",
    is_flag=True,
    default=False,
    help="Allow destructive restore or bootstrap workflows on prod instances (break-glass only).",
)
def restore(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    no_sanitize: bool,
    allow_prod_data_workflow: bool,
) -> None:
    platform_commands_workflow.execute_restore_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        no_sanitize=no_sanitize,
        allow_prod_data_workflow=allow_prod_data_workflow,
        run_workflow_fn=_run_workflow,
    )


@main.command(
    "bootstrap",
    help=f"Reset database and filestore state, then initialize a fresh runtime. {DESTRUCTIVE_DATA_WORKFLOW_HELP}",
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option(
    "--allow-prod-data-workflow",
    is_flag=True,
    default=False,
    help="Allow destructive restore or bootstrap workflows on prod instances (break-glass only).",
)
def bootstrap(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    no_sanitize: bool,
    allow_prod_data_workflow: bool,
) -> None:
    platform_commands_workflow.execute_bootstrap_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        no_sanitize=no_sanitize,
        allow_prod_data_workflow=allow_prod_data_workflow,
        run_workflow_fn=_run_workflow,
    )


@main.command(
    "init",
    help=f"Initialize modules in the existing local runtime database. {LOCAL_RUNTIME_CONTRACT_HELP}",
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option(
    "--allow-prod-data-workflow",
    is_flag=True,
    default=False,
    help="Allow init workflow on prod instances (break-glass only).",
)
def init(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    allow_prod_data_workflow: bool,
) -> None:
    platform_commands_workflow.execute_init_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        allow_prod_data_workflow=allow_prod_data_workflow,
        assert_prod_data_workflow_allowed_fn=_assert_prod_data_workflow_allowed,
        run_init_workflow_fn=_run_init_workflow,
    )


@main.command(
    "openupgrade",
    help=f"Run the local OpenUpgrade workflow. {LOCAL_RUNTIME_CONTRACT_HELP}",
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True, default=False)
@click.option("--reset-versions", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
def openupgrade(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
) -> None:
    platform_commands_workflow.execute_openupgrade_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
        run_openupgrade_command_fn=_run_openupgrade_command,
    )


@main.command(
    "update",
    help=f"Apply module updates against the local runtime. {LOCAL_RUNTIME_CONTRACT_HELP}",
)
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
def update(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None, dry_run: bool) -> None:
    platform_commands_workflow.execute_update_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
        run_update_workflow_fn=_run_update_workflow,
    )


if __name__ == "__main__":
    main()
