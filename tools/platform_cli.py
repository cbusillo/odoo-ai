from __future__ import annotations

import json
import os
import subprocess
import textwrap
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

import click
import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.stack_restore import restore_stack

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
type JsonObject = dict[str, JsonValue]


PLATFORM_RUNTIME_ENV_KEYS = (
    "PLATFORM_CONTEXT",
    "PLATFORM_INSTANCE",
    "PLATFORM_RUNTIME_ENV_FILE",
    "PYTHON_VERSION",
    "ODOO_VERSION",
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
    "RESTORE_SSH_DIR",
    "OPENUPGRADE_ENABLED",
    "OPENUPGRADE_SCRIPTS_PATH",
    "OPENUPGRADE_TARGET_VERSION",
    "OPENUPGRADE_SKIP_UPDATE_ADDONS",
    "GITHUB_TOKEN",
)

PLATFORM_RUNTIME_PASSTHROUGH_PREFIXES = (
    "ENV_OVERRIDE_",
)

PLATFORM_RUNTIME_PASSTHROUGH_KEYS = (
    "ODOO_KEY",
)

ENV_COLLISION_MODE_ENV_KEY = "PLATFORM_ENV_COLLISION_MODE"
VALID_ENV_COLLISION_MODES = ("warn", "error", "ignore")

PLATFORM_RUN_WORKFLOWS = (
    "restore",
    "init",
    "update",
    "openupgrade",
    "restore-init",
    "restore-update",
    "restore-init-update",
)

PLATFORM_TUI_WORKFLOWS = (
    "select",
    "info",
    "status",
    "up",
    "build",
    *PLATFORM_RUN_WORKFLOWS,
)

GHCR_HOST = "ghcr.io"
DEFAULT_ODOO_BASE_RUNTIME_IMAGE = "ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime"
DEFAULT_ODOO_BASE_DEVTOOLS_IMAGE = "ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools"
DEFAULT_DOKPLOY_DEPLOY_TIMEOUT_SECONDS = 600
DEFAULT_DOKPLOY_HEALTH_TIMEOUT_SECONDS = 180
DEFAULT_DOKPLOY_HEALTHCHECK_PATH = "/web/health"
DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF = "main"
HEALTHCHECK_PASS_STATUSES = {"pass", "ok", "healthy"}
REGISTRY_LOGINS_DONE: set[tuple[str, str]] = set()
VERIFIED_IMAGE_ACCESS: set[str] = set()


class ContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str | None = None
    install_modules: tuple[str, ...] = ()
    addon_repositories_add: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    update_modules: str = "AUTO"
    instances: dict[str, "InstanceDefinition"] = Field(default_factory=dict)


class InstanceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str | None = None
    addon_repositories_add: tuple[str, ...] = ()
    install_modules_add: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)


class DokployTargetDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: str
    instance: str
    target_type: Literal["compose", "application"] = "compose"
    target_id: str = ""
    target_name: str = ""
    git_branch: str = ""
    source_git_ref: str = DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF
    auto_deploy: bool | None = None
    require_test_gate: bool = False
    require_prod_gate: bool = False
    deploy_timeout_seconds: int | None = Field(default=None, ge=1)
    healthcheck_enabled: bool = True
    healthcheck_path: str = DEFAULT_DOKPLOY_HEALTHCHECK_PATH
    healthcheck_timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] = Field(default_factory=dict)
    domains: tuple[str, ...] = ()


class DokploySourceOfTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    targets: tuple[DokployTargetDefinition, ...] = ()


class StackDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    odoo_version: str
    state_root: str = ""
    addons_path: tuple[str, ...]
    addon_repositories: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    required_env_keys: tuple[str, ...] = ()
    contexts: dict[str, ContextDefinition]


@dataclass(frozen=True)
class ShipBranchSyncPlan:
    source_git_ref: str
    source_commit: str
    target_branch: str
    remote_branch_commit_before: str
    branch_update_required: bool


class PlatformSecretsInstanceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: dict[str, str | int | float | bool] = Field(default_factory=dict)


class PlatformSecretsContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared: dict[str, str | int | float | bool] = Field(default_factory=dict)
    instances: dict[str, PlatformSecretsInstanceDefinition] = Field(default_factory=dict)


class PlatformSecretsDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    shared: dict[str, str | int | float | bool] = Field(default_factory=dict)
    contexts: dict[str, PlatformSecretsContextDefinition] = Field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentLayer:
    name: str
    values: dict[str, str]


@dataclass(frozen=True)
class EnvironmentCollision:
    key: str
    previous_layer: str
    incoming_layer: str


@dataclass(frozen=True)
class LoadedEnvironment:
    env_file_path: Path
    merged_values: dict[str, str]
    source_by_key: dict[str, str]
    collisions: tuple[EnvironmentCollision, ...]


@dataclass(frozen=True)
class LoadedStack:
    stack_file_path: Path
    stack_definition: StackDefinition


@dataclass(frozen=True)
class RuntimeSelection:
    context_name: str
    instance_name: str
    context_definition: ContextDefinition
    instance_definition: InstanceDefinition
    database_name: str
    project_name: str
    state_path: Path
    data_mount: Path
    runtime_conf_host_path: Path
    data_volume_name: str
    log_volume_name: str
    db_volume_name: str
    web_host_port: int
    longpoll_host_port: int
    db_host_port: int
    runtime_odoo_conf_path: str
    effective_install_modules: tuple[str, ...]
    effective_addon_repositories: tuple[str, ...]
    effective_runtime_env: dict[str, str]


def _discover_repo_root(start_directory: Path) -> Path:
    current_directory = start_directory.resolve()
    for candidate_path in (current_directory, *current_directory.parents):
        if (candidate_path / ".git").exists() or (candidate_path / "pyproject.toml").exists():
            return candidate_path
    return current_directory


def _parse_env_file(env_file_path: Path) -> dict[str, str]:
    parsed_values: dict[str, str] = {}
    for raw_line in env_file_path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if "=" not in stripped_line:
            continue
        key_part, value_part = stripped_line.split("=", 1)
        environment_key = key_part.strip()
        environment_value = value_part.strip()
        if len(environment_value) >= 2 and environment_value[0] == environment_value[-1] and environment_value[0] in {'"', "'"}:
            environment_value = environment_value[1:-1]
        if " #" in environment_value:
            environment_value = environment_value.split(" #", 1)[0].rstrip()
        parsed_values[environment_key] = environment_value
    return parsed_values


def _resolve_platform_secrets_file(repo_root: Path) -> Path:
    return repo_root / "platform" / "secrets.toml"


def _normalize_secret_env_values(raw_values: dict[str, str | int | float | bool]) -> dict[str, str]:
    normalized_values: dict[str, str] = {}
    for environment_key, raw_value in raw_values.items():
        if isinstance(raw_value, bool):
            normalized_values[environment_key] = "True" if raw_value else "False"
            continue
        normalized_values[environment_key] = str(raw_value)
    return normalized_values


def _load_platform_secrets_definition(
    repo_root: Path,
) -> PlatformSecretsDefinition | None:
    platform_secrets_file = _resolve_platform_secrets_file(repo_root)
    if not platform_secrets_file.exists():
        return None

    loaded_data = tomllib.loads(platform_secrets_file.read_text(encoding="utf-8"))
    try:
        return PlatformSecretsDefinition.model_validate(loaded_data)
    except ValidationError as error:
        message = error.json(indent=2)
        raise click.ClickException(f"Invalid secrets file: {platform_secrets_file}\n{message}") from error


def _resolve_env_collision_mode(collision_mode: str | None) -> str:
    if collision_mode is not None:
        normalized_mode = collision_mode.strip().lower()
    else:
        normalized_mode = os.environ.get(ENV_COLLISION_MODE_ENV_KEY, "warn").strip().lower()

    if normalized_mode not in VALID_ENV_COLLISION_MODES:
        allowed_values = ", ".join(VALID_ENV_COLLISION_MODES)
        raise click.ClickException(
            f"Invalid {ENV_COLLISION_MODE_ENV_KEY}='{normalized_mode}'. Expected one of: {allowed_values}."
        )
    return normalized_mode


def _build_environment_layers(
    *,
    repo_root: Path,
    env_file_path: Path,
    context_name: str | None,
    instance_name: str | None,
) -> list[EnvironmentLayer]:
    environment_layers: list[EnvironmentLayer] = [
        EnvironmentLayer(name=f"env-file:{env_file_path}", values=_parse_env_file(env_file_path)),
    ]
    platform_secrets = _load_platform_secrets_definition(repo_root)
    if platform_secrets is None:
        return environment_layers

    shared_values = _normalize_secret_env_values(platform_secrets.shared)
    if shared_values:
        environment_layers.append(EnvironmentLayer(name="secrets.shared", values=shared_values))

    if context_name is None:
        return environment_layers

    context_overrides = platform_secrets.contexts.get(context_name)
    if context_overrides is None:
        return environment_layers

    context_values = _normalize_secret_env_values(context_overrides.shared)
    if context_values:
        environment_layers.append(EnvironmentLayer(name=f"secrets.contexts.{context_name}.shared", values=context_values))

    if instance_name is None:
        return environment_layers

    instance_overrides = context_overrides.instances.get(instance_name)
    if instance_overrides is None:
        return environment_layers

    instance_values = _normalize_secret_env_values(instance_overrides.env)
    if instance_values:
        environment_layers.append(
            EnvironmentLayer(
                name=f"secrets.contexts.{context_name}.instances.{instance_name}.env",
                values=instance_values,
            )
        )
    return environment_layers


def _merge_environment_layers(environment_layers: list[EnvironmentLayer]) -> tuple[dict[str, str], dict[str, str], tuple[EnvironmentCollision, ...]]:
    merged_values: dict[str, str] = {}
    source_by_key: dict[str, str] = {}
    collisions: list[EnvironmentCollision] = []

    for environment_layer in environment_layers:
        for environment_key, environment_value in environment_layer.values.items():
            if environment_key in merged_values and merged_values[environment_key] != environment_value:
                collisions.append(
                    EnvironmentCollision(
                        key=environment_key,
                        previous_layer=source_by_key[environment_key],
                        incoming_layer=environment_layer.name,
                    )
                )
            merged_values[environment_key] = environment_value
            source_by_key[environment_key] = environment_layer.name

    return merged_values, source_by_key, tuple(collisions)


def _handle_environment_collisions(collisions: tuple[EnvironmentCollision, ...], collision_mode: str) -> None:
    if not collisions or collision_mode == "ignore":
        return

    lines = [
        "Environment key collisions detected across layers:",
    ]
    for collision in collisions:
        lines.append(f"- {collision.key}: {collision.previous_layer} -> {collision.incoming_layer}")
    lines.append(f"Set {ENV_COLLISION_MODE_ENV_KEY}=ignore to suppress this warning.")
    message = "\n".join(lines)

    if collision_mode == "error":
        raise click.ClickException(message)

    click.echo(f"warning: {message}", err=True)


def _load_environment_with_details(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> LoadedEnvironment:
    env_file_path = env_file if env_file is not None else _resolve_default_env_file(repo_root)
    if not env_file_path.is_absolute():
        env_file_path = repo_root / env_file_path
    if not env_file_path.exists():
        raise click.ClickException(f"Env file not found: {env_file_path}")

    normalized_collision_mode = _resolve_env_collision_mode(collision_mode)
    environment_layers = _build_environment_layers(
        repo_root=repo_root,
        env_file_path=env_file_path,
        context_name=context_name,
        instance_name=instance_name,
    )
    merged_values, source_by_key, collisions = _merge_environment_layers(environment_layers)
    _handle_environment_collisions(collisions, normalized_collision_mode)
    return LoadedEnvironment(
        env_file_path=env_file_path,
        merged_values=merged_values,
        source_by_key=source_by_key,
        collisions=collisions,
    )


def _load_environment(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> tuple[Path, dict[str, str]]:
    loaded_environment = _load_environment_with_details(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode=collision_mode,
    )
    return loaded_environment.env_file_path, loaded_environment.merged_values


def _load_stack(stack_file_path: Path) -> LoadedStack:
    loaded_data = tomllib.loads(stack_file_path.read_text(encoding="utf-8"))
    try:
        stack_definition = StackDefinition.model_validate(loaded_data)
    except ValidationError as error:
        message = error.json(indent=2)
        raise click.ClickException(f"Invalid stack file: {stack_file_path}\n{message}") from error
    return LoadedStack(stack_file_path=stack_file_path, stack_definition=stack_definition)


def _load_dokploy_source_of_truth(source_file_path: Path) -> DokploySourceOfTruth:
    loaded_data = tomllib.loads(source_file_path.read_text(encoding="utf-8"))
    try:
        return DokploySourceOfTruth.model_validate(loaded_data)
    except ValidationError as error:
        message = error.json(indent=2)
        raise click.ClickException(f"Invalid Dokploy source file: {source_file_path}\n{message}") from error


def _resolve_default_env_file(repo_root: Path) -> Path:
    root_env_file = repo_root / ".env"
    if root_env_file.exists():
        return root_env_file
    platform_env_file = repo_root / "platform" / ".env"
    if platform_env_file.exists():
        return platform_env_file
    return root_env_file


def _merge_effective_modules(context_definition: ContextDefinition, instance_definition: InstanceDefinition) -> tuple[str, ...]:
    effective_install_modules: list[str] = []
    for module_name in context_definition.install_modules:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    for module_name in instance_definition.install_modules_add:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    return tuple(effective_install_modules)


def _merge_effective_addon_repositories(
    stack_definition: StackDefinition,
    context_definition: ContextDefinition,
    instance_definition: InstanceDefinition,
) -> tuple[str, ...]:
    effective_addon_repositories: list[str] = []
    for repository_name in stack_definition.addon_repositories:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    for repository_name in context_definition.addon_repositories_add:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    for repository_name in instance_definition.addon_repositories_add:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    return tuple(effective_addon_repositories)


def _merge_effective_runtime_env(
    stack_definition: StackDefinition,
    context_definition: ContextDefinition,
    instance_definition: InstanceDefinition,
) -> dict[str, str]:
    effective_runtime_env: dict[str, str] = {}
    runtime_sources = (
        stack_definition.runtime_env,
        context_definition.runtime_env,
        instance_definition.runtime_env,
    )
    for runtime_source in runtime_sources:
        for key, raw_value in runtime_source.items():
            effective_runtime_env[key] = str(raw_value)
    return effective_runtime_env


def _port_seed_for_context(context_name: str) -> tuple[int, int, int]:
    context_port_map = {
        "opw": (8069, 8072, 15432),
        "cm": (9069, 9072, 25432),
        "qc": (10069, 10072, 35432),
    }
    return context_port_map.get(context_name, (11069, 11072, 45432))


def _port_offset_for_instance(instance_name: str) -> int:
    instance_offset_map = {
        "local": 0,
        "dev": 100,
        "testing": 200,
        "prod": 300,
    }
    return instance_offset_map.get(instance_name, 0)


def _resolve_local_platform_state_root(stack_definition: StackDefinition) -> Path:
    if stack_definition.state_root.strip():
        expanded_state_root = Path(os.path.expanduser(stack_definition.state_root))
        if expanded_state_root.is_absolute():
            return expanded_state_root
        return (_discover_repo_root(Path.cwd()) / expanded_state_root).resolve()
    return (_discover_repo_root(Path.cwd()) / ".platform" / "state").resolve()


def _resolve_runtime_selection(stack_definition: StackDefinition, context_name: str, instance_name: str) -> RuntimeSelection:
    if context_name not in stack_definition.contexts:
        available_contexts = ", ".join(sorted(stack_definition.contexts))
        raise click.ClickException(f"Unknown context '{context_name}'. Available: {available_contexts}")

    context_definition = stack_definition.contexts[context_name]
    instance_definition = context_definition.instances.get(instance_name, InstanceDefinition())
    database_name = instance_definition.database or context_definition.database or context_name
    effective_install_modules = _merge_effective_modules(context_definition, instance_definition)
    effective_addon_repositories = _merge_effective_addon_repositories(
        stack_definition,
        context_definition,
        instance_definition,
    )
    effective_runtime_env = _merge_effective_runtime_env(
        stack_definition,
        context_definition,
        instance_definition,
    )

    base_web_port, base_longpoll_port, base_db_port = _port_seed_for_context(context_name)
    instance_offset = _port_offset_for_instance(instance_name)
    web_host_port = base_web_port + instance_offset
    longpoll_host_port = base_longpoll_port + instance_offset
    db_host_port = base_db_port + instance_offset

    state_root_path = _resolve_local_platform_state_root(stack_definition)
    state_path = state_root_path / f"{context_name}-{instance_name}"
    data_volume_name = f"odoo-{context_name}-{instance_name}-data"
    log_volume_name = f"odoo-{context_name}-{instance_name}-logs"
    db_volume_name = f"odoo-{context_name}-{instance_name}-db"

    return RuntimeSelection(
        context_name=context_name,
        instance_name=instance_name,
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name=database_name,
        project_name=f"odoo-{context_name}-{instance_name}",
        state_path=state_path,
        data_mount=state_path / "data",
        runtime_conf_host_path=state_path / "data" / "platform.odoo.conf",
        data_volume_name=data_volume_name,
        log_volume_name=log_volume_name,
        db_volume_name=db_volume_name,
        web_host_port=web_host_port,
        longpoll_host_port=longpoll_host_port,
        db_host_port=db_host_port,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=effective_install_modules,
        effective_addon_repositories=effective_addon_repositories,
        effective_runtime_env=effective_runtime_env,
    )


def _write_runtime_odoo_conf_file(
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    runtime_selection.runtime_conf_host_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_conf_file = runtime_selection.runtime_conf_host_path

    lines: list[str] = ["[options]"]
    lines.append(f"db_name = {runtime_selection.database_name}")
    lines.append(f"db_user = {source_environment.get('ODOO_DB_USER', 'odoo')}")
    lines.append(f"db_password = {source_environment.get('ODOO_DB_PASSWORD', '')}")
    lines.append("db_host = database")
    lines.append("db_port = 5432")
    lines.append("list_db = False")
    lines.append(f"addons_path = {','.join(stack_definition.addons_path)}")
    lines.append("data_dir = /volumes/data")
    lines.append("")
    lines.append(f"; context={runtime_selection.context_name}")
    lines.append(f"; instance={runtime_selection.instance_name}")
    lines.append(f"; install_modules={','.join(runtime_selection.effective_install_modules)}")

    runtime_conf_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_conf_file


PLATFORM_ENV_BLOCK_START = "# >>> platform managed runtime"
PLATFORM_ENV_BLOCK_END = "# <<< platform managed runtime"


def _sync_root_env_with_runtime(repo_root: Path, runtime_values: dict[str, str]) -> Path:
    root_env_file = repo_root / ".env"
    existing_content = ""
    if root_env_file.exists():
        existing_content = root_env_file.read_text(encoding="utf-8")

    existing_lines = existing_content.splitlines()
    updated_lines: list[str] = []
    inside_managed_block = False
    for existing_line in existing_lines:
        stripped_line = existing_line.strip()
        if stripped_line == PLATFORM_ENV_BLOCK_START:
            inside_managed_block = True
            continue
        if stripped_line == PLATFORM_ENV_BLOCK_END:
            inside_managed_block = False
            continue
        if inside_managed_block:
            continue
        updated_lines.append(existing_line)

    while updated_lines and not updated_lines[-1].strip():
        updated_lines.pop()
    if updated_lines:
        updated_lines.append("")

    updated_lines.append(PLATFORM_ENV_BLOCK_START)
    updated_lines.append("# Generated by `uv run platform ...`; do not edit this block manually.")
    for key, value in runtime_values.items():
        updated_lines.append(f"{key}={value}")
    updated_lines.append(PLATFORM_ENV_BLOCK_END)
    updated_lines.append("")

    root_env_file.write_text("\n".join(updated_lines), encoding="utf-8")
    return root_env_file


def _build_runtime_env_values(
    runtime_env_file: Path,
    stack_definition: StackDefinition,
    runtime_selection: RuntimeSelection,
    source_environment: dict[str, str],
) -> dict[str, str]:
    runtime_values = {
        "PLATFORM_CONTEXT": runtime_selection.context_name,
        "PLATFORM_INSTANCE": runtime_selection.instance_name,
        "PLATFORM_RUNTIME_ENV_FILE": str(runtime_env_file),
        "PYTHON_VERSION": source_environment.get("PYTHON_VERSION", "3.13"),
        "ODOO_VERSION": stack_definition.odoo_version,
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
        "ODOO_MASTER_PASSWORD": source_environment.get("ODOO_MASTER_PASSWORD", ""),
        "ODOO_INSTALL_MODULES": ",".join(runtime_selection.effective_install_modules),
        "ODOO_ADDON_REPOSITORIES": ",".join(runtime_selection.effective_addon_repositories),
        "ODOO_UPDATE_MODULES": runtime_selection.context_definition.update_modules,
        "ODOO_ADDONS_PATH": ",".join(stack_definition.addons_path),
        "ODOO_WEB_HOST_PORT": str(runtime_selection.web_host_port),
        "ODOO_LONGPOLL_HOST_PORT": str(runtime_selection.longpoll_host_port),
        "ODOO_DB_HOST_PORT": str(runtime_selection.db_host_port),
        "ODOO_LIST_DB": "False",
        "ODOO_WEB_COMMAND": f"python3 /volumes/scripts/run_odoo_bootstrap.py -c {runtime_selection.runtime_odoo_conf_path}",
        "RESTORE_SSH_DIR": source_environment.get("RESTORE_SSH_DIR", str(Path.home() / ".ssh")),
        "OPENUPGRADE_ENABLED": source_environment.get("OPENUPGRADE_ENABLED", "False"),
        "OPENUPGRADE_SCRIPTS_PATH": source_environment.get("OPENUPGRADE_SCRIPTS_PATH", ""),
        "OPENUPGRADE_TARGET_VERSION": source_environment.get("OPENUPGRADE_TARGET_VERSION", ""),
        "OPENUPGRADE_SKIP_UPDATE_ADDONS": source_environment.get("OPENUPGRADE_SKIP_UPDATE_ADDONS", "True"),
        "GITHUB_TOKEN": source_environment.get("GITHUB_TOKEN", ""),
    }

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
    return "\n".join(f"{key}={value}" for key, value in runtime_values.items()) + "\n"


def _runtime_env_diff(existing_values: dict[str, str], proposed_values: dict[str, str]) -> JsonObject:
    added_keys = sorted(key for key in proposed_values if key not in existing_values)
    removed_keys = sorted(key for key in existing_values if key not in proposed_values)
    changed_keys = sorted(
        key for key in proposed_values if key in existing_values and proposed_values[key] != existing_values[key]
    )
    unchanged_count = len(proposed_values) - len(added_keys) - len(changed_keys)
    return {
        "added_keys": cast(JsonValue, added_keys),
        "removed_keys": cast(JsonValue, removed_keys),
        "changed_keys": cast(JsonValue, changed_keys),
        "unchanged_key_count": unchanged_count,
    }


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
    _sync_root_env_with_runtime(repo_root, runtime_values)
    return runtime_env_file


def _compose_base_command(runtime_env_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(runtime_env_file),
        "-f",
        "docker-compose.yml",
        "-f",
        "docker/config/base.yaml",
        "-f",
        "docker-compose.override.yml",
    ]


def _clean_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _extract_registry_host(image_reference: str) -> str | None:
    candidate = image_reference.strip()
    if not candidate:
        return None
    without_digest = candidate.split("@", 1)[0]
    first_segment = without_digest.split("/", 1)[0]
    if "." in first_segment or ":" in first_segment or first_segment == "localhost":
        return first_segment.lower()
    return None


def _extract_registry_owner(image_reference: str) -> str | None:
    candidate = image_reference.strip()
    if not candidate:
        return None
    without_digest = candidate.split("@", 1)[0]
    first_segment, separator, remainder = without_digest.partition("/")
    if not separator:
        return None
    if not ("." in first_segment or ":" in first_segment or first_segment == "localhost"):
        return None
    owner, owner_separator, _package_name = remainder.partition("/")
    if owner_separator and owner:
        return owner
    return None


def _resolve_base_images_for_registry_auth(environment_values: dict[str, str]) -> list[str]:
    runtime_image = _clean_optional_value(environment_values.get("ODOO_BASE_RUNTIME_IMAGE"))
    devtools_image = _clean_optional_value(environment_values.get("ODOO_BASE_DEVTOOLS_IMAGE"))

    if runtime_image is None:
        runtime_image = DEFAULT_ODOO_BASE_RUNTIME_IMAGE
    if devtools_image is None:
        devtools_image = DEFAULT_ODOO_BASE_DEVTOOLS_IMAGE

    images: list[str] = []
    for image in (runtime_image, devtools_image):
        if image and image not in images:
            images.append(image)
    return images


def _resolve_ghcr_username(environment_values: dict[str, str], image_reference: str) -> str | None:
    candidates = (
        environment_values.get("GHCR_USERNAME"),
        os.environ.get("GHCR_USERNAME"),
        environment_values.get("GITHUB_ACTOR"),
        os.environ.get("GITHUB_ACTOR"),
        _extract_registry_owner(image_reference),
    )
    for candidate in candidates:
        cleaned = _clean_optional_value(candidate)
        if cleaned:
            return cleaned
    return None


def _resolve_ghcr_token(environment_values: dict[str, str]) -> str | None:
    candidates = (
        environment_values.get("GHCR_TOKEN"),
        os.environ.get("GHCR_TOKEN"),
        environment_values.get("GHCR_READ_TOKEN"),
        os.environ.get("GHCR_READ_TOKEN"),
        environment_values.get("GITHUB_TOKEN"),
        os.environ.get("GITHUB_TOKEN"),
    )
    for candidate in candidates:
        cleaned = _clean_optional_value(candidate)
        if cleaned:
            return cleaned

    gh_token_result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if gh_token_result.returncode == 0:
        gh_token = _clean_optional_value(gh_token_result.stdout)
        if gh_token:
            return gh_token
    return None


def _verify_base_image_access(image_reference: str) -> None:
    if image_reference in VERIFIED_IMAGE_ACCESS:
        return
    inspect_result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", image_reference],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect_result.returncode != 0:
        details = _clean_optional_value(inspect_result.stderr) or _clean_optional_value(inspect_result.stdout)
        raise click.ClickException(
            "Unable to read base image metadata for "
            f"'{image_reference}'. Ensure the GHCR token grants read access to the package."
            + (f"\nDocker reported: {details}" if details else ""),
        )
    VERIFIED_IMAGE_ACCESS.add(image_reference)


def _ensure_registry_auth_for_base_images(environment_values: dict[str, str]) -> None:
    images = _resolve_base_images_for_registry_auth(environment_values)
    ghcr_images = [image for image in images if _extract_registry_host(image) == GHCR_HOST]
    if not ghcr_images:
        return

    ghcr_username = _resolve_ghcr_username(environment_values, ghcr_images[0])
    ghcr_token = _resolve_ghcr_token(environment_values)

    if not ghcr_username:
        raise click.ClickException(
            "Missing GHCR username for private base image pull. Set GHCR_USERNAME in .env "
            "or provide GITHUB_ACTOR in the current shell.",
        )
    if not ghcr_token:
        raise click.ClickException(
            "Missing GHCR token for private base image pull. Set GHCR_TOKEN (preferred) "
            "or GITHUB_TOKEN in .env with read:packages access.",
        )

    login_key = (GHCR_HOST, ghcr_username)
    if login_key not in REGISTRY_LOGINS_DONE:
        login_result = subprocess.run(
            ["docker", "login", GHCR_HOST, "-u", ghcr_username, "--password-stdin"],
            input=f"{ghcr_token}\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if login_result.returncode != 0:
            details = _clean_optional_value(login_result.stderr) or _clean_optional_value(login_result.stdout)
            raise click.ClickException(
                "Docker login to GHCR failed. Ensure the token is valid and has package read permissions."
                + (f"\nDocker reported: {details}" if details else ""),
            )
        REGISTRY_LOGINS_DONE.add(login_key)

    for image in ghcr_images:
        _verify_base_image_access(image)


def _run_command(command: list[str]) -> None:
    result = subprocess.run(command, check=False, env=_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}")


def _run_command_best_effort(command: list[str]) -> int:
    result = subprocess.run(command, check=False, env=_command_execution_env())
    return result.returncode


def _run_command_with_input(command: list[str], input_text: str) -> None:
    result = subprocess.run(command, input=input_text.encode("utf-8"), check=False, env=_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}")


def _run_command_capture(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=_command_execution_env())
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


def _parse_compose_ps_output(raw_output: str) -> list[JsonObject]:
    stripped_output = raw_output.strip()
    if not stripped_output:
        return []

    try:
        parsed_payload = json.loads(stripped_output)
    except ValueError:
        parsed_payload = None

    parsed_objects: list[JsonObject] = []
    if isinstance(parsed_payload, list):
        for item in parsed_payload:
            parsed_item = _as_json_object(cast(JsonValue, item))
            if parsed_item is not None:
                parsed_objects.append(parsed_item)
        return parsed_objects
    if isinstance(parsed_payload, dict):
        parsed_item = _as_json_object(cast(JsonValue, parsed_payload))
        if parsed_item is not None:
            parsed_objects.append(parsed_item)
        return parsed_objects

    for raw_line in stripped_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            line_payload = json.loads(line)
        except ValueError:
            continue
        parsed_item = _as_json_object(cast(JsonValue, line_payload))
        if parsed_item is not None:
            parsed_objects.append(parsed_item)
    return parsed_objects


def _as_int(value: JsonValue) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _normalize_compose_service_status(service_payload: JsonObject) -> JsonObject:
    published_ports: list[JsonValue] = []
    publishers_payload = service_payload.get("Publishers")
    if isinstance(publishers_payload, list):
        for publisher in publishers_payload:
            publisher_payload = _as_json_object(cast(JsonValue, publisher))
            if publisher_payload is None:
                continue
            published_ports.append(
                {
                    "url": str(publisher_payload.get("URL") or ""),
                    "protocol": str(publisher_payload.get("Protocol") or ""),
                    "target_port": _as_int(cast(JsonValue, publisher_payload.get("TargetPort"))),
                    "published_port": _as_int(cast(JsonValue, publisher_payload.get("PublishedPort"))),
                }
            )

    return {
        "name": str(service_payload.get("Name") or ""),
        "service": str(service_payload.get("Service") or ""),
        "state": str(service_payload.get("State") or "").lower(),
        "status": str(service_payload.get("Status") or ""),
        "health": str(service_payload.get("Health") or ""),
        "exit_code": _as_int(cast(JsonValue, service_payload.get("ExitCode"))),
        "published_ports": published_ports,
    }


def _local_runtime_status(runtime_env_file: Path) -> JsonObject:
    status_payload: JsonObject = {
        "runtime_env_file": str(runtime_env_file),
        "runtime_env_exists": runtime_env_file.exists(),
        "project_running": False,
        "running_services": 0,
        "services": [],
    }
    if not runtime_env_file.exists():
        status_payload["state"] = "not_selected"
        return status_payload

    compose_command = _compose_base_command(runtime_env_file)
    try:
        raw_output = _run_command_capture(compose_command + ["ps", "--format", "json"])
    except click.ClickException as error:
        status_payload["state"] = "error"
        status_payload["compose_error"] = error.message
        return status_payload

    services = [_normalize_compose_service_status(item) for item in _parse_compose_ps_output(raw_output)]
    running_services = [
        service_payload
        for service_payload in services
        if str(service_payload.get("state") or "").lower() == "running"
    ]
    status_payload["state"] = "running" if running_services else "stopped"
    status_payload["project_running"] = bool(running_services)
    status_payload["running_services"] = len(running_services)
    status_payload["services"] = cast(JsonValue, services)
    return status_payload


def _resolve_dokploy_target(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    ship_mode: str,
) -> tuple[str, str, str, click.ClickException | None, click.ClickException | None]:
    compose_resolution_error: click.ClickException | None = None
    app_resolution_error: click.ClickException | None = None

    selected_target_type = ""
    selected_target_id = ""
    selected_target_name = ""

    if ship_mode in {"auto", "compose"}:
        try:
            compose_id, compose_name = _resolve_dokploy_compose_id(
                host=host,
                token=token,
                context_name=context_name,
                instance_name=instance_name,
                environment_values=environment_values,
            )
            selected_target_type = "compose"
            selected_target_id = compose_id
            selected_target_name = compose_name
        except click.ClickException as error:
            compose_resolution_error = error
            if ship_mode == "compose":
                raise

    if not selected_target_type:
        try:
            application_id, app_name = _resolve_dokploy_application_id(
                host=host,
                token=token,
                context_name=context_name,
                instance_name=instance_name,
                environment_values=environment_values,
            )
            selected_target_type = "application"
            selected_target_id = application_id
            selected_target_name = app_name
        except click.ClickException as error:
            app_resolution_error = error

    return (
        selected_target_type,
        selected_target_id,
        selected_target_name,
        compose_resolution_error,
        app_resolution_error,
    )


def _summarize_deployment(deployment: JsonObject | None) -> JsonObject | None:
    if deployment is None:
        return None
    summary: JsonObject = {
        "deployment_id": _deployment_key(deployment),
        "status": _deployment_status(deployment),
    }
    for source_key, target_key in (
        ("createdAt", "created_at"),
        ("title", "title"),
        ("description", "description"),
        ("logPath", "log_path"),
    ):
        value = deployment.get(source_key)
        if value is not None:
            summary[target_key] = cast(JsonValue, value)
    return summary


def _dokploy_status_payload(
    *,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> JsonObject:
    payload: JsonObject = {
        "enabled": context_name in {"cm", "opw"} and instance_name in {"dev", "testing", "prod"},
        "target_type": "",
        "target_name": "",
        "target_id": "",
    }
    if not payload["enabled"]:
        payload["reason"] = "Dokploy status is only evaluated for cm/opw dev/testing/prod targets."
        return payload

    try:
        host, token = _read_dokploy_config(environment_values)
    except click.ClickException as error:
        payload["error"] = error.message
        return payload

    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    payload["ship_mode"] = ship_mode

    (
        target_type,
        target_id,
        target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = _resolve_dokploy_target(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        ship_mode=ship_mode,
    )

    if not target_type:
        payload["error"] = "No Dokploy deployment target resolved."
        if compose_resolution_error is not None:
            payload["compose_error"] = compose_resolution_error.message
        if app_resolution_error is not None:
            payload["application_error"] = app_resolution_error.message
        return payload

    payload["target_type"] = target_type
    payload["target_name"] = target_name
    payload["target_id"] = target_id

    if target_type == "compose":
        compose_payload = _dokploy_request(
            host=host,
            token=token,
            path="/api/compose.one",
            query={"composeId": target_id},
        )
        compose_payload_as_object = _as_json_object(compose_payload)
        if compose_payload_as_object is not None:
            payload["compose_status"] = cast(JsonValue, compose_payload_as_object.get("composeStatus"))
            payload["source_type"] = cast(JsonValue, compose_payload_as_object.get("sourceType"))
            payload["server_id"] = cast(JsonValue, compose_payload_as_object.get("serverId"))
            payload["app_name"] = cast(JsonValue, compose_payload_as_object.get("appName"))
        payload["latest_deployment"] = _summarize_deployment(_latest_deployment_for_compose(host, token, target_id))
        return payload

    payload["latest_deployment"] = _summarize_deployment(_latest_deployment_for_application(host, token, target_id))
    return payload


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
) -> tuple[str, str, str]:
    normalized_target_type = target_type.strip().lower()
    if normalized_target_type not in {"auto", "compose", "application"}:
        raise click.ClickException("target-type must be one of: auto, compose, application.")

    if normalized_target_type == "compose":
        compose_id, compose_name = _resolve_dokploy_compose_id(
            host=host,
            token=token,
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )
        return "compose", compose_id, compose_name

    if normalized_target_type == "application":
        application_id, app_name = _resolve_dokploy_application_id(
            host=host,
            token=token,
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )
        return "application", application_id, app_name

    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    (
        selected_target_type,
        selected_target_id,
        selected_target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = _resolve_dokploy_target(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        ship_mode=ship_mode,
    )
    if selected_target_type:
        return selected_target_type, selected_target_id, selected_target_name

    details: list[str] = ["No Dokploy deployment target resolved."]
    if compose_resolution_error is not None:
        details.append(f"compose_error={compose_resolution_error.message}")
    if app_resolution_error is not None:
        details.append(f"application_error={app_resolution_error.message}")
    raise click.ClickException(" ".join(details))


def _parse_dokploy_env_text(raw_env_text: str) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for raw_line in raw_env_text.splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if stripped_line.startswith("export "):
            stripped_line = stripped_line[7:].strip()
        if "=" not in stripped_line:
            continue
        key_part, value_part = stripped_line.split("=", 1)
        env_key = key_part.strip()
        env_value = value_part
        env_map[env_key] = env_value
    return env_map


def _serialize_dokploy_env_text(env_map: dict[str, str]) -> str:
    if not env_map:
        return ""
    rendered_lines = [f"{env_key}={env_value}" for env_key, env_value in env_map.items()]
    return "\n".join(rendered_lines)


def _fetch_dokploy_target_payload(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
) -> JsonObject:
    if target_type == "compose":
        payload = _dokploy_request(
            host=host,
            token=token,
            path="/api/compose.one",
            query={"composeId": target_id},
        )
    elif target_type == "application":
        payload = _dokploy_request(
            host=host,
            token=token,
            path="/api/application.one",
            query={"applicationId": target_id},
        )
    else:
        raise click.ClickException(f"Unsupported target type: {target_type}")

    payload_as_object = _as_json_object(payload)
    if payload_as_object is None:
        raise click.ClickException(f"Dokploy {target_type}.one returned an invalid response payload.")
    return payload_as_object


def _update_dokploy_target_env(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
    target_payload: JsonObject,
    env_text: str,
) -> None:
    if target_type == "compose":
        _dokploy_request(
            host=host,
            token=token,
            path="/api/compose.update",
            method="POST",
            payload={"composeId": target_id, "env": env_text},
        )
        return

    if target_type == "application":
        build_args = target_payload.get("buildArgs")
        build_secrets = target_payload.get("buildSecrets")
        create_env_file = target_payload.get("createEnvFile")
        _dokploy_request(
            host=host,
            token=token,
            path="/api/application.saveEnvironment",
            method="POST",
            payload={
                "applicationId": target_id,
                "env": env_text,
                "buildArgs": str(build_args) if isinstance(build_args, str) else "",
                "buildSecrets": str(build_secrets) if isinstance(build_secrets, str) else "",
                "createEnvFile": bool(create_env_file) if isinstance(create_env_file, bool) else True,
            },
        )
        return

    raise click.ClickException(f"Unsupported target type: {target_type}")


def _resolve_dokploy_runtime(
    *,
    repo_root: Path,
    env_file: Path | None,
    context_name: str,
    instance_name: str,
    target_type: str,
) -> tuple[str, str, str, str, str, dict[str, str]]:
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
    )
    return host, token, resolved_target_type, resolved_target_id, resolved_target_name, environment_values


def _resolve_dokploy_source_file(repo_root: Path, source_file: Path | None) -> Path:
    resolved_source_file = source_file if source_file is not None else (repo_root / "platform" / "dokploy.toml")
    if not resolved_source_file.is_absolute():
        resolved_source_file = repo_root / resolved_source_file
    if not resolved_source_file.exists():
        raise click.ClickException(f"Dokploy source-of-truth file not found: {resolved_source_file}")
    return resolved_source_file


def _load_dokploy_source_of_truth_if_present(repo_root: Path) -> DokploySourceOfTruth | None:
    source_file_path = repo_root / "platform" / "dokploy.toml"
    if not source_file_path.exists():
        return None
    return _load_dokploy_source_of_truth(source_file_path)


def _find_dokploy_target_definition(
    source_of_truth: DokploySourceOfTruth,
    *,
    context_name: str,
    instance_name: str,
) -> DokployTargetDefinition | None:
    for target in source_of_truth.targets:
        if target.context == context_name and target.instance == instance_name:
            return target
    return None


def _run_gate_command(command: list[str], *, dry_run: bool) -> None:
    if dry_run:
        click.echo(f"$ {' '.join(command)}")
        return
    _run_command(command)


def _run_required_gates(
    *,
    context_name: str,
    target_definition: DokployTargetDefinition | None,
    dry_run: bool,
    skip_gate: bool,
) -> None:
    if skip_gate or target_definition is None:
        return

    if target_definition.require_test_gate:
        _run_gate_command(["uv", "run", "test", "run", "--json", "--stack", context_name], dry_run=dry_run)

    if target_definition.require_prod_gate:
        _run_gate_command(["uv", "run", "prod-gate", "backup", "--target", context_name], dry_run=dry_run)


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


def _normalize_domains(raw_domains: JsonValue) -> list[str]:
    if not isinstance(raw_domains, list):
        return []
    normalized_domains: list[str] = []
    for domain_item in raw_domains:
        domain_payload = _as_json_object(domain_item)
        if domain_payload is None:
            continue
        host = str(domain_payload.get("host") or "").strip()
        if host and host not in normalized_domains:
            normalized_domains.append(host)
    return normalized_domains


def _resolve_restore_explicit_env_file(*, repo_root: Path, env_file: Path | None) -> Path | None:
    if env_file is None:
        return None

    resolved_env_file = env_file if env_file.is_absolute() else (repo_root / env_file)
    if not resolved_env_file.exists():
        raise click.ClickException(f"Env file not found: {resolved_env_file}")
    return resolved_env_file


def _run_restore_workflow(
    *,
    repo_root: Path,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    bootstrap_only: bool,
    no_sanitize: bool,
    dry_run: bool,
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Restore workflow is currently supported only for cm/opw contexts.")

    restore_stack_name = context_name if instance_name == "local" else f"{context_name}-{instance_name}"
    restore_env_file = _resolve_restore_explicit_env_file(repo_root=repo_root, env_file=env_file)
    if restore_env_file is None:
        stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
        if not stack_file_path.exists():
            raise click.ClickException(f"Stack file not found: {stack_file_path}")
        loaded_stack = _load_stack(stack_file_path)
        runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
        _env_file_path, loaded_environment = _load_environment(
            repo_root,
            None,
            context_name=context_name,
            instance_name=instance_name,
        )
        _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)
        restore_env_file = _write_runtime_env_file(
            repo_root,
            loaded_stack.stack_definition,
            runtime_selection,
            loaded_environment,
        )

    if dry_run:
        restore_env_label = str(restore_env_file) if restore_env_file is not None else "<default stack env>"
        click.echo(f"restore_context={context_name}")
        click.echo(f"restore_instance={instance_name}")
        click.echo(f"restore_stack={restore_stack_name}")
        click.echo(f"restore_env_file={restore_env_label}")
        click.echo(f"restore_bootstrap_only={str(bootstrap_only).lower()}")
        click.echo(f"restore_no_sanitize={str(no_sanitize).lower()}")
        return

    restore_exit_code = restore_stack(
        restore_stack_name,
        env_file=restore_env_file,
        bootstrap_only=bootstrap_only,
        no_sanitize=no_sanitize,
    )
    if restore_exit_code != 0:
        raise click.ClickException(f"Restore failed with exit code {restore_exit_code}.")


def _ensure_runtime_env_file(repo_root: Path, context_name: str, instance_name: str) -> Path:
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )
    return runtime_env_file


def _openupgrade_exec_command(*, force: bool, reset_versions: bool) -> list[str]:
    command = [
        "python3",
        "/volumes/scripts/run_openupgrade.py",
    ]
    if force:
        command.append("--force")
    if reset_versions:
        command.append("--reset-versions")
    return command


def _run_openupgrade_workflow(
    *,
    runtime_env_file: Path,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
) -> None:
    compose_command = _compose_base_command(runtime_env_file)
    openupgrade_command = _openupgrade_exec_command(force=force, reset_versions=reset_versions)

    up_script_runner_command = compose_command + ["up", "-d", "script-runner"]
    stop_web_command = compose_command + ["stop", "web"]
    openupgrade_exec_command = compose_command + ["exec", "-T", "script-runner", *openupgrade_command]
    up_web_command = compose_command + ["up", "-d", "web"]

    if dry_run:
        click.echo(f"$ {' '.join(up_script_runner_command)}")
        click.echo(f"$ {' '.join(stop_web_command)}")
        click.echo(f"$ {' '.join(openupgrade_exec_command)}")
        click.echo(f"$ {' '.join(up_web_command)}")
        return

    _run_command(up_script_runner_command)
    _run_command_best_effort(stop_web_command)
    try:
        _run_command(up_script_runner_command)
        _run_command(openupgrade_exec_command)
    finally:
        _run_command_best_effort(up_web_command)


def _run_init_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = _ensure_runtime_env_file(repo_root, context_name, instance_name)

    install_modules = ",".join(runtime_selection.effective_install_modules)
    addons_path_argument = ",".join(loaded_stack.stack_definition.addons_path)
    command = [
        "/odoo/odoo-bin",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "-i",
        install_modules,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    if dry_run:
        compose_command = _compose_base_command(runtime_env_file)
        _run_with_web_temporarily_stopped(
            runtime_env_file,
            operation=lambda: None,
            dry_run=True,
            dry_run_commands=(compose_command + ["exec", "-T", "script-runner", *command],),
        )
        return

    def _run_init_operation() -> None:
        _compose_exec(runtime_env_file, "script-runner", command)
        _apply_admin_password_if_configured(
            runtime_env_file,
            runtime_selection,
            loaded_stack.stack_definition,
            loaded_environment,
        )
        _assert_active_admin_password_is_not_default(
            runtime_env_file,
            runtime_selection,
            loaded_stack.stack_definition,
            loaded_environment,
        )

    _run_with_web_temporarily_stopped(
        runtime_env_file,
        operation=_run_init_operation,
        dry_run=False,
        dry_run_commands=(),
    )
    click.echo(f"init={runtime_selection.project_name}")


def _run_update_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = _ensure_runtime_env_file(repo_root, context_name, instance_name)

    update_modules = runtime_selection.context_definition.update_modules
    module_argument = ",".join(runtime_selection.effective_install_modules)
    addons_path_argument = ",".join(loaded_stack.stack_definition.addons_path)
    if update_modules.upper() != "AUTO":
        module_argument = update_modules

    command = [
        "/odoo/odoo-bin",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "-u",
        module_argument,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    if dry_run:
        compose_command = _compose_base_command(runtime_env_file)
        _run_with_web_temporarily_stopped(
            runtime_env_file,
            operation=lambda: None,
            dry_run=True,
            dry_run_commands=(compose_command + ["exec", "-T", "script-runner", *command],),
        )
        return

    _run_with_web_temporarily_stopped(
        runtime_env_file,
        operation=lambda: _compose_exec(runtime_env_file, "script-runner", command),
        dry_run=False,
        dry_run_commands=(),
    )
    click.echo(f"update={runtime_selection.project_name}")


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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = _load_stack(stack_file_path)
    _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = _ensure_runtime_env_file(repo_root, context_name, instance_name)
    _run_openupgrade_workflow(
        runtime_env_file=runtime_env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
    )
    if not dry_run:
        click.echo(f"openupgrade={context_name}-{instance_name}")


def _ordered_instance_names(context_definition: ContextDefinition) -> list[str]:
    preferred_order = ("local", "dev", "testing", "prod")
    ordered_names = [instance_name for instance_name in preferred_order if instance_name in context_definition.instances]
    for instance_name in sorted(context_definition.instances):
        if instance_name not in ordered_names:
            ordered_names.append(instance_name)
    return ordered_names


def _run_workflow_phase(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    phase: str,
    dry_run: bool,
    no_cache: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
) -> None:
    click.echo(f"workflow_phase_start={phase}")
    _run_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=phase,
        dry_run=dry_run,
        no_cache=no_cache,
        bootstrap_only=bootstrap_only,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
    )
    click.echo(f"workflow_phase_end={phase}")


def _run_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
) -> None:
    normalized_workflow = workflow.strip().lower()
    if normalized_workflow == "restore":
        repo_root = _discover_repo_root(Path.cwd())
        _run_restore_workflow(
            repo_root=repo_root,
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            dry_run=dry_run,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "init":
        _run_init_workflow(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            dry_run=dry_run,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "update":
        _run_update_workflow(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            dry_run=dry_run,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "openupgrade":
        _run_openupgrade_command(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            force=force,
            reset_versions=reset_versions,
            dry_run=dry_run,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-init":
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="restore",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="init",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-update":
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="restore",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="update",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-init-update":
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="restore-init",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        _run_workflow_phase(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            phase="update",
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "select":
        _invoke_platform_command(
            "select",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "info":
        _invoke_platform_command(
            "info",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            json_output=False,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "status":
        _invoke_platform_command(
            "status",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            json_output=False,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "up":
        _invoke_platform_command(
            "up",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            build=True,
            no_cache=no_cache,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "build":
        _invoke_platform_command(
            "build",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            no_cache=no_cache,
        )
        click.echo(f"workflow={normalized_workflow}")
        return

    raise click.ClickException(f"Unsupported workflow: {workflow}")


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
) -> JsonValue:
    normalized_host = host.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{normalized_host}{normalized_path}"
    headers = {"x-api-key": token}
    response = requests.request(method, url, headers=headers, json=payload, params=query, timeout=60)
    if response.status_code >= 400:
        body = response.text.strip()
        raise click.ClickException(f"Dokploy API {method} {normalized_path} failed ({response.status_code}): {body}")
    if not response.content:
        return {}
    try:
        parsed_payload = response.json()
        return cast(JsonValue, parsed_payload)
    except ValueError:
        return {"raw": response.text}


def _read_dokploy_config(environment_values: dict[str, str]) -> tuple[str, str]:
    host = environment_values.get("DOKPLOY_HOST", "").strip()
    token = environment_values.get("DOKPLOY_TOKEN", "").strip()
    if not host or not token:
        raise click.ClickException("Missing DOKPLOY_HOST or DOKPLOY_TOKEN in .env.")
    return host, token


def _as_json_object(value: JsonValue) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return cast(JsonObject, value)


def _extract_deployments(raw_payload: JsonValue) -> list[JsonObject]:
    if isinstance(raw_payload, list):
        deployment_items: list[JsonObject] = []
        for item in raw_payload:
            item_as_object = _as_json_object(item)
            if item_as_object is not None:
                deployment_items.append(item_as_object)
        return deployment_items
    if isinstance(raw_payload, dict):
        for key in ("data", "deployments", "items", "result"):
            value = raw_payload.get(key)
            if isinstance(value, list):
                deployment_items = []
                for item in value:
                    item_as_object = _as_json_object(item)
                    if item_as_object is not None:
                        deployment_items.append(item_as_object)
                return deployment_items
    return []


def _deployment_key(deployment: JsonObject) -> str:
    for key in ("deploymentId", "deployment_id", "id", "uuid"):
        value = deployment.get(key)
        if value:
            return str(value)
    return ""


def _deployment_status(deployment: JsonObject) -> str:
    for key in ("status", "state", "deploymentStatus"):
        value = deployment.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def _collect_application_records(payload: JsonValue) -> list[JsonObject]:
    records: list[JsonObject] = []
    seen_pairs: set[tuple[str, str]] = set()

    def walk(node: JsonValue) -> None:
        if isinstance(node, dict):
            application_id = node.get("applicationId") or node.get("application_id")
            display_name = node.get("name")
            internal_name = node.get("appName")
            if application_id is not None:
                for candidate_name in (display_name, internal_name):
                    if not isinstance(candidate_name, str) or not candidate_name:
                        continue
                    pair = (str(application_id), str(candidate_name))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    records.append(
                        {
                            "application_id": str(application_id),
                            "app_name": str(candidate_name),
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return records


def _resolve_dokploy_app_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_APP_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def _resolve_dokploy_compose_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_COMPOSE_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def _collect_compose_records(payload: JsonValue) -> list[JsonObject]:
    records: list[JsonObject] = []
    seen_pairs: set[tuple[str, str]] = set()

    def walk(node: JsonValue) -> None:
        if isinstance(node, dict):
            compose_id = node.get("composeId") or node.get("compose_id")
            display_name = node.get("name")
            internal_name = node.get("appName")
            if compose_id is not None:
                for candidate_name in (display_name, internal_name):
                    if not isinstance(candidate_name, str) or not candidate_name:
                        continue
                    pair = (str(compose_id), candidate_name)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    records.append(
                        {
                            "compose_id": str(compose_id),
                            "compose_name": candidate_name,
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return records


def _resolve_dokploy_compose_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_COMPOSE_ID_{context_name}_{instance_name}".upper()
    explicit_compose_id = environment_values.get(specific_id_key, "").strip()
    compose_name = _resolve_dokploy_compose_name(context_name, instance_name, environment_values)
    if explicit_compose_id:
        return explicit_compose_id, compose_name

    projects_payload = _dokploy_request(host=host, token=token, path="/api/project.all")
    records = _collect_compose_records(projects_payload)
    matches = [record for record in records if record.get("compose_name") == compose_name]
    if not matches:
        specific_name_key = f"DOKPLOY_COMPOSE_NAME_{context_name}_{instance_name}".upper()
        known_names = sorted(
            {
                record_name
                for record in records
                for record_name in (record.get("compose_name"),)
                if isinstance(record_name, str) and record_name
            }
        )
        preview = ", ".join(known_names[:20])
        raise click.ClickException(
            f"Dokploy compose '{compose_name}' not found. Set {specific_id_key}=<composeId> or "
            f"{specific_name_key}=<name>. Known: {preview}"
        )
    if len(matches) > 1:
        raise click.ClickException(
            f"Multiple Dokploy compose entries match '{compose_name}'. "
            f"Set {specific_id_key}=<composeId> to disambiguate."
        )
    matched_compose_id = matches[0].get("compose_id")
    if not isinstance(matched_compose_id, str) or not matched_compose_id:
        raise click.ClickException(
            f"Dokploy compose '{compose_name}' returned an invalid compose id. Use {specific_id_key}=<composeId>."
        )
    return matched_compose_id, compose_name


def _resolve_dokploy_ship_mode(
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> str:
    specific_key = f"DOKPLOY_SHIP_MODE_{context_name}_{instance_name}".upper()
    configured_mode = environment_values.get(specific_key, "").strip().lower()
    if not configured_mode:
        configured_mode = environment_values.get("DOKPLOY_SHIP_MODE", "auto").strip().lower() or "auto"
    if configured_mode not in {"auto", "compose", "application"}:
        raise click.ClickException(
            f"Invalid Dokploy ship mode '{configured_mode}'. Expected auto, compose, or application."
        )
    return configured_mode


def _resolve_dokploy_application_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_APPLICATION_ID_{context_name}_{instance_name}".upper()
    explicit_application_id = environment_values.get(specific_id_key, "").strip()
    app_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
    if explicit_application_id:
        return explicit_application_id, app_name

    projects_payload = _dokploy_request(host=host, token=token, path="/api/project.all")
    records = _collect_application_records(projects_payload)
    matches = [record for record in records if record.get("app_name") == app_name]
    if not matches:
        specific_name_key = f"DOKPLOY_APP_NAME_{context_name}_{instance_name}".upper()
        known_names = sorted(
            {
                record_name
                for record in records
                for record_name in (record.get("app_name"),)
                if isinstance(record_name, str) and record_name
            }
        )
        preview = ", ".join(known_names[:20])
        raise click.ClickException(
            f"Dokploy app '{app_name}' not found. Set {specific_id_key}=<applicationId> or "
            f"{specific_name_key}=<name>. Known: {preview}"
        )
    if len(matches) > 1:
        raise click.ClickException(
            f"Multiple Dokploy apps match '{app_name}'. Set {specific_id_key}=<applicationId> to disambiguate."
        )
    matched_application_id = matches[0].get("application_id")
    if not isinstance(matched_application_id, str) or not matched_application_id:
        raise click.ClickException(
            f"Dokploy app '{app_name}' returned an invalid application id. Use {specific_id_key}=<applicationId>."
        )
    return matched_application_id, app_name


def _latest_deployment_for_application(host: str, token: str, application_id: str) -> JsonObject | None:
    payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = _extract_deployments(payload)
    if not deployments:
        return None

    def sort_key(item: JsonObject) -> str:
        for key in ("createdAt", "created_at", "updatedAt", "updated_at"):
            value = item.get(key)
            if value:
                return str(value)
        return _deployment_key(item)

    return max(deployments, key=sort_key)


def _latest_deployment_for_compose(host: str, token: str, compose_id: str) -> JsonObject | None:
    compose_payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/compose.one",
        query={"composeId": compose_id},
    )
    if not isinstance(compose_payload, dict):
        return None
    deployments_payload = compose_payload.get("deployments")
    if not isinstance(deployments_payload, list):
        return None

    deployments: list[JsonObject] = []
    for item in deployments_payload:
        item_as_object = _as_json_object(cast(JsonValue, item))
        if item_as_object is not None:
            deployments.append(item_as_object)
    if not deployments:
        return None

    def sort_key(item: JsonObject) -> str:
        for key in ("createdAt", "created_at", "updatedAt", "updated_at"):
            value = item.get(key)
            if value:
                return str(value)
        return _deployment_key(item)

    return max(deployments, key=sort_key)


def _collect_rollback_ids(payload: JsonValue | list[JsonObject]) -> list[str]:
    rollback_ids: list[str] = []

    def walk(node: JsonValue | list[JsonObject]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = key.lower()
                if normalized_key in {"rollbackid", "rollback_id"} and isinstance(value, (str, int, float)):
                    candidate = str(value)
                    if candidate not in rollback_ids:
                        rollback_ids.append(candidate)
                if normalized_key == "rollback" and isinstance(value, dict):
                    nested_id = value.get("rollbackId") or value.get("id")
                    if isinstance(nested_id, (str, int, float)):
                        candidate = str(nested_id)
                        if candidate not in rollback_ids:
                            rollback_ids.append(candidate)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return rollback_ids


def _wait_for_dokploy_deployment(
    *,
    host: str,
    token: str,
    application_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    success_statuses = {"success", "succeeded", "done", "completed", "healthy", "finished"}
    failure_statuses = {"failed", "error", "canceled", "cancelled", "killed", "unhealthy", "timeout"}

    start_time = time.monotonic()
    while time.monotonic() - start_time <= timeout_seconds:
        latest = _latest_deployment_for_application(host, token, application_id)
        if not latest:
            time.sleep(3)
            continue

        latest_key = _deployment_key(latest)
        latest_status = _deployment_status(latest)
        if latest_key and latest_key != before_key:
            if latest_status in success_statuses:
                return f"deployment={latest_key} status={latest_status}"
            if latest_status in failure_statuses:
                raise click.ClickException(f"Dokploy deployment failed: deployment={latest_key} status={latest_status}")
            if not latest_status:
                return f"deployment={latest_key} status=unknown"
        time.sleep(3)

    raise click.ClickException("Timed out waiting for Dokploy deployment status.")


def _wait_for_dokploy_compose_deployment(
    *,
    host: str,
    token: str,
    compose_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    success_statuses = {"success", "succeeded", "done", "completed", "healthy", "finished"}
    failure_statuses = {"failed", "error", "canceled", "cancelled", "killed", "unhealthy", "timeout"}

    start_time = time.monotonic()
    while time.monotonic() - start_time <= timeout_seconds:
        latest = _latest_deployment_for_compose(host, token, compose_id)
        if not latest:
            time.sleep(3)
            continue

        latest_key = _deployment_key(latest)
        latest_status = _deployment_status(latest)
        if latest_key and latest_key != before_key:
            if latest_status in success_statuses:
                return f"deployment={latest_key} status={latest_status}"
            if latest_status in failure_statuses:
                raise click.ClickException(f"Dokploy compose deployment failed: deployment={latest_key} status={latest_status}")
            if not latest_status:
                return f"deployment={latest_key} status=unknown"
        time.sleep(3)

    raise click.ClickException("Timed out waiting for Dokploy compose deployment status.")


def _resolve_ship_timeout_seconds(
    *,
    timeout_override_seconds: int | None,
    target_definition: DokployTargetDefinition | None,
) -> int:
    if timeout_override_seconds is not None:
        if timeout_override_seconds <= 0:
            raise click.ClickException("Ship timeout must be greater than zero seconds.")
        return timeout_override_seconds

    if target_definition is not None and target_definition.deploy_timeout_seconds is not None:
        return target_definition.deploy_timeout_seconds
    return DEFAULT_DOKPLOY_DEPLOY_TIMEOUT_SECONDS


def _resolve_ship_health_timeout_seconds(
    *,
    health_timeout_override_seconds: int | None,
    target_definition: DokployTargetDefinition | None,
) -> int:
    if health_timeout_override_seconds is not None:
        if health_timeout_override_seconds <= 0:
            raise click.ClickException("Ship health timeout must be greater than zero seconds.")
        return health_timeout_override_seconds

    if target_definition is not None and target_definition.healthcheck_timeout_seconds is not None:
        return target_definition.healthcheck_timeout_seconds
    return DEFAULT_DOKPLOY_HEALTH_TIMEOUT_SECONDS


def _normalize_healthcheck_path(raw_healthcheck_path: str) -> str:
    normalized_path = raw_healthcheck_path.strip() or DEFAULT_DOKPLOY_HEALTHCHECK_PATH
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return normalized_path


def _resolve_healthcheck_base_urls(
    *,
    target_definition: DokployTargetDefinition | None,
    environment_values: dict[str, str],
) -> tuple[str, ...]:
    raw_base_urls: list[str] = []
    if target_definition is not None:
        raw_base_urls.extend(domain for domain in target_definition.domains if domain)

    if not raw_base_urls:
        fallback_base_url = environment_values.get("ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL", "").strip()
        if fallback_base_url:
            raw_base_urls.append(fallback_base_url)

    normalized_base_urls: list[str] = []
    for raw_base_url in raw_base_urls:
        stripped_base_url = raw_base_url.strip()
        if not stripped_base_url:
            continue
        parsed_base_url = urlparse(stripped_base_url)
        if not parsed_base_url.scheme:
            stripped_base_url = f"https://{stripped_base_url}"
        stripped_base_url = stripped_base_url.rstrip("/")
        if stripped_base_url and stripped_base_url not in normalized_base_urls:
            normalized_base_urls.append(stripped_base_url)

    return tuple(normalized_base_urls)


def _resolve_ship_healthcheck_urls(
    *,
    target_definition: DokployTargetDefinition | None,
    environment_values: dict[str, str],
) -> tuple[str, ...]:
    if target_definition is not None and not target_definition.healthcheck_enabled:
        return ()

    healthcheck_path = _normalize_healthcheck_path(
        target_definition.healthcheck_path if target_definition is not None else DEFAULT_DOKPLOY_HEALTHCHECK_PATH
    )
    base_urls = _resolve_healthcheck_base_urls(target_definition=target_definition, environment_values=environment_values)
    return tuple(f"{base_url}{healthcheck_path}" for base_url in base_urls)


def _wait_for_ship_healthcheck(*, url: str, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_result = "no response"

    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=5)
        except requests.RequestException as error:
            last_result = str(error)
            time.sleep(2)
            continue

        if response.status_code != 200:
            last_result = f"http {response.status_code}"
            time.sleep(2)
            continue

        try:
            payload = response.json()
        except ValueError:
            return "http 200"

        if isinstance(payload, dict) and "status" in payload:
            normalized_status = str(payload.get("status") or "").strip().lower()
            if normalized_status in HEALTHCHECK_PASS_STATUSES:
                return f"http 200 status={normalized_status}"
            last_result = f"http 200 status={normalized_status or 'unknown'}"
            time.sleep(2)
            continue

        return "http 200"

    raise click.ClickException(f"Health check failed for {url}. Last result: {last_result}")


def _verify_ship_healthchecks(*, urls: tuple[str, ...], timeout_seconds: int) -> None:
    for healthcheck_url in urls:
        click.echo(f"healthcheck_url={healthcheck_url}")
        result = _wait_for_ship_healthcheck(url=healthcheck_url, timeout_seconds=timeout_seconds)
        click.echo(f"healthcheck_result={result}")


def _render_odoo_config(
    *,
    stack_definition: StackDefinition,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    include_comments: bool,
) -> str:
    runtime_selection = _resolve_runtime_selection(stack_definition, context_name, instance_name)

    lines: list[str] = ["[options]"]
    lines.append(f"db_name = {runtime_selection.database_name}")
    lines.append(f"db_user = {environment_values.get('ODOO_DB_USER', 'odoo')}")
    lines.append(f"db_password = {environment_values.get('ODOO_DB_PASSWORD', '')}")
    lines.append("db_host = database")
    lines.append("db_port = 5432")
    lines.append("list_db = False")
    lines.append(f"addons_path = {','.join(stack_definition.addons_path)}")
    lines.append(f"data_dir = {runtime_selection.data_mount}")

    if include_comments:
        lines.append("")
        lines.append(f"; context={context_name}")
        lines.append(f"; instance={instance_name}")
        lines.append(f"; install_modules={','.join(runtime_selection.effective_install_modules)}")
        lines.append(f"; update_modules={runtime_selection.context_definition.update_modules}")

    return "\n".join(lines) + "\n"


@click.group(help="Minimal platform contract CLI.")
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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    env_file_path, parsed_environment = _load_environment(repo_root, env_file)
    missing_keys: list[str] = []
    for required_key in loaded_stack.stack_definition.required_env_keys:
        if not parsed_environment.get(required_key):
            missing_keys.append(required_key)

    click.echo(f"stack_file={loaded_stack.stack_file_path}")
    click.echo(f"env_file={env_file_path}")
    click.echo(f"schema_version={loaded_stack.stack_definition.schema_version}")
    click.echo(f"contexts={','.join(sorted(loaded_stack.stack_definition.contexts))}")

    if missing_keys:
        formatted_missing_keys = ", ".join(missing_keys)
        raise click.ClickException(f"Missing required env keys: {formatted_missing_keys}")

    click.echo("validation=ok")


@main.command("list-contexts")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--json-output", is_flag=True, default=False)
def list_contexts(stack_file: Path, json_output: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    context_names = sorted(loaded_stack.stack_definition.contexts)

    if json_output:
        click.echo(json.dumps({"contexts": context_names}, indent=2))
        return

    for context_name in context_names:
        click.echo(context_name)


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

    rendered_keys: list[JsonObject] = []
    keys_by_source: dict[str, list[str]] = {}
    for environment_key in sorted(loaded_environment.merged_values):
        source_layer = loaded_environment.source_by_key.get(environment_key, "")
        keys_by_source.setdefault(source_layer, []).append(environment_key)
        rendered_key: JsonObject = {
            "key": environment_key,
            "source": source_layer,
        }
        rendered_key["value"] = loaded_environment.merged_values[environment_key] if show_values else "<redacted>"
        rendered_keys.append(rendered_key)

    rendered_collisions: list[JsonObject] = []
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
        "collisions": cast(JsonValue, rendered_collisions),
        "merged_key_count": len(loaded_environment.merged_values),
        "keys_by_source": cast(JsonValue, keys_by_source),
        "keys": cast(JsonValue, rendered_keys),
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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )

    loaded_stack = _load_stack(stack_file_path)
    rendered_config = _render_odoo_config(
        stack_definition=loaded_stack.stack_definition,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=loaded_environment,
        include_comments=include_comments,
    )

    output_file_path = output_file if output_file.is_absolute() else (repo_root / output_file)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(rendered_config, encoding="utf-8")
    click.echo(f"wrote={output_file_path}")


@main.command("doctor")
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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    payload: JsonObject = {
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
        "install_modules": cast(JsonValue, list(runtime_selection.effective_install_modules)),
        "addon_repositories": cast(JsonValue, list(runtime_selection.effective_addon_repositories)),
        "root_env_file": str(env_file_path),
        "runtime_env_file": str(runtime_env_file),
        "local_runtime": _local_runtime_status(runtime_env_file),
        "dokploy": _dokploy_status_payload(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        ),
    }

    _emit_payload(payload, json_output=json_output)


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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"

    missing_required_env_keys = [
        required_key
        for required_key in loaded_stack.stack_definition.required_env_keys
        if not environment_values.get(required_key, "").strip()
    ]

    payload: JsonObject = {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "project_name": runtime_selection.project_name,
        "state_path": str(runtime_selection.state_path),
        "runtime_conf_host_path": str(runtime_selection.runtime_conf_host_path),
        "runtime_env_file": str(runtime_env_file),
        "runtime_env_exists": runtime_env_file.exists(),
        "root_env_file": str(env_file_path),
        "required_env_keys": cast(JsonValue, list(loaded_stack.stack_definition.required_env_keys)),
        "missing_required_env_keys": cast(JsonValue, missing_required_env_keys),
        "data_volume": runtime_selection.data_volume_name,
        "log_volume": runtime_selection.log_volume_name,
        "db_volume": runtime_selection.db_volume_name,
        "web_host_port": runtime_selection.web_host_port,
        "longpoll_host_port": runtime_selection.longpoll_host_port,
        "db_host_port": runtime_selection.db_host_port,
        "install_modules": cast(JsonValue, list(runtime_selection.effective_install_modules)),
        "addon_repositories": cast(JsonValue, list(runtime_selection.effective_addon_repositories)),
        "dokploy": _dokploy_status_payload(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        ),
    }

    _emit_payload(payload, json_output=json_output)


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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"

    payload: JsonObject = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "project_name": runtime_selection.project_name,
        "local": _local_runtime_status(runtime_env_file),
        "dokploy": _dokploy_status_payload(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        ),
    }

    _emit_payload(payload, json_output=json_output)


@main.command("run")
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
@click.option("--bootstrap-only", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.option("--reset-versions", is_flag=True, default=False)
def run_workflow(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
) -> None:
    _run_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        bootstrap_only=bootstrap_only,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
    )


@main.command("tui")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", default=None)
@click.option("--instance", "instance_name", default=None)
@click.option("--workflow", default=None, type=click.Choice(PLATFORM_TUI_WORKFLOWS, case_sensitive=False))
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-cache", is_flag=True, default=False)
@click.option("--bootstrap-only", is_flag=True, default=False)
@click.option("--no-sanitize", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.option("--reset-versions", is_flag=True, default=False)
def tui(
    stack_file: Path,
    context_name: str | None,
    instance_name: str | None,
    workflow: str | None,
    env_file: Path | None,
    dry_run: bool,
    no_cache: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    context_names = sorted(loaded_stack.stack_definition.contexts)
    if not context_names:
        raise click.ClickException("No contexts found in stack definition.")

    selected_context_name = context_name
    if selected_context_name is None:
        selected_context_name = click.prompt(
            "Select context",
            type=click.Choice(context_names, case_sensitive=False),
        )
    if selected_context_name not in loaded_stack.stack_definition.contexts:
        raise click.ClickException(f"Unknown context '{selected_context_name}'.")

    context_definition = loaded_stack.stack_definition.contexts[selected_context_name]
    available_instance_names = _ordered_instance_names(context_definition)
    if not available_instance_names:
        raise click.ClickException(f"Context '{selected_context_name}' has no instances.")

    selected_instance_name = instance_name
    if selected_instance_name is None:
        selected_instance_name = click.prompt(
            "Select instance",
            type=click.Choice(available_instance_names, case_sensitive=False),
            default="local" if "local" in available_instance_names else available_instance_names[0],
            show_default=True,
        )
    if selected_instance_name not in context_definition.instances:
        raise click.ClickException(
            f"Unknown instance '{selected_instance_name}' for context '{selected_context_name}'."
        )

    selected_workflow = workflow
    if selected_workflow is None:
        selected_workflow = click.prompt(
            "Select workflow",
            type=click.Choice(PLATFORM_TUI_WORKFLOWS, case_sensitive=False),
            default="status",
            show_default=True,
        )

    _run_workflow(
        stack_file=stack_file,
        context_name=selected_context_name,
        instance_name=selected_instance_name,
        env_file=env_file,
        workflow=selected_workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        bootstrap_only=bootstrap_only,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
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
    repo_root = _discover_repo_root(Path.cwd())
    host, token, resolved_target_type, resolved_target_id, resolved_target_name, _environment_values = _resolve_dokploy_runtime(
        repo_root=repo_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        target_type=target_type,
    )
    target_payload = _fetch_dokploy_target_payload(
        host=host,
        token=token,
        target_type=resolved_target_type,
        target_id=resolved_target_id,
    )
    env_map = _parse_dokploy_env_text(str(target_payload.get("env") or ""))

    selected_keys: list[str] = []
    requested_keys = set(keys)
    for env_key in env_map:
        include_key = not requested_keys and not prefixes
        if env_key in requested_keys:
            include_key = True
        if any(env_key.startswith(prefix) for prefix in prefixes):
            include_key = True
        if include_key:
            selected_keys.append(env_key)

    rendered_env: dict[str, str] = {}
    for env_key in selected_keys:
        if show_values:
            rendered_env[env_key] = env_map[env_key]
        else:
            rendered_env[env_key] = "<redacted>"

    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "target_type": resolved_target_type,
        "target_id": resolved_target_id,
        "target_name": resolved_target_name,
        "total_env_keys": len(env_map),
        "matched_env_keys": len(selected_keys),
        "show_values": show_values,
        "env": cast(JsonValue, rendered_env),
    }
    _emit_payload(payload, json_output=json_output)


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
    parsed_assignments: dict[str, str] = {}
    for assignment in assignments:
        env_key, env_value = _parse_env_assignment(assignment)
        parsed_assignments[env_key] = env_value

    repo_root = _discover_repo_root(Path.cwd())
    host, token, resolved_target_type, resolved_target_id, resolved_target_name, _environment_values = _resolve_dokploy_runtime(
        repo_root=repo_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        target_type=target_type,
    )
    target_payload = _fetch_dokploy_target_payload(
        host=host,
        token=token,
        target_type=resolved_target_type,
        target_id=resolved_target_id,
    )
    env_map = _parse_dokploy_env_text(str(target_payload.get("env") or ""))

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    for env_key, env_value in parsed_assignments.items():
        current_value = env_map.get(env_key)
        if current_value == env_value:
            unchanged_keys.append(env_key)
            continue
        env_map[env_key] = env_value
        changed_keys.append(env_key)

    if changed_keys and not dry_run:
        _update_dokploy_target_env(
            host=host,
            token=token,
            target_type=resolved_target_type,
            target_id=resolved_target_id,
            target_payload=target_payload,
            env_text=_serialize_dokploy_env_text(env_map),
        )

    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "target_type": resolved_target_type,
        "target_id": resolved_target_id,
        "target_name": resolved_target_name,
        "requested_keys": cast(JsonValue, list(parsed_assignments.keys())),
        "changed_keys": cast(JsonValue, changed_keys),
        "unchanged_keys": cast(JsonValue, unchanged_keys),
        "updated": bool(changed_keys) and not dry_run,
        "dry_run": dry_run,
    }
    _emit_payload(payload, json_output=json_output)


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
    if not keys and not prefixes:
        raise click.ClickException("Specify at least one --key or --prefix for env-unset.")

    repo_root = _discover_repo_root(Path.cwd())
    host, token, resolved_target_type, resolved_target_id, resolved_target_name, _environment_values = _resolve_dokploy_runtime(
        repo_root=repo_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        target_type=target_type,
    )
    target_payload = _fetch_dokploy_target_payload(
        host=host,
        token=token,
        target_type=resolved_target_type,
        target_id=resolved_target_id,
    )
    env_map = _parse_dokploy_env_text(str(target_payload.get("env") or ""))

    removed_keys: list[str] = []
    requested_keys = set(keys)
    for env_key in list(env_map.keys()):
        if env_key in requested_keys or any(env_key.startswith(prefix) for prefix in prefixes):
            env_map.pop(env_key, None)
            removed_keys.append(env_key)

    if removed_keys and not dry_run:
        _update_dokploy_target_env(
            host=host,
            token=token,
            target_type=resolved_target_type,
            target_id=resolved_target_id,
            target_payload=target_payload,
            env_text=_serialize_dokploy_env_text(env_map),
        )

    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "target_type": resolved_target_type,
        "target_id": resolved_target_id,
        "target_name": resolved_target_name,
        "removed_keys": cast(JsonValue, removed_keys),
        "updated": bool(removed_keys) and not dry_run,
        "dry_run": dry_run,
    }
    _emit_payload(payload, json_output=json_output)


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
    if limit <= 0:
        raise click.ClickException("--limit must be greater than zero.")

    repo_root = _discover_repo_root(Path.cwd())
    host, token, resolved_target_type, resolved_target_id, resolved_target_name, _environment_values = _resolve_dokploy_runtime(
        repo_root=repo_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        target_type=target_type,
    )

    deployment_payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.allByType",
        query={"type": resolved_target_type, "id": resolved_target_id},
    )
    deployments = _extract_deployments(deployment_payload)

    def _deployment_sort_key(item: JsonObject) -> str:
        created_at = item.get("createdAt")
        return str(created_at or "")

    deployment_items = sorted(deployments, key=_deployment_sort_key, reverse=True)[:limit]
    rendered_deployments: list[JsonObject] = []
    for deployment_item in deployment_items:
        deployment_summary = _summarize_deployment(deployment_item) or {}
        for key_name, output_key in (
            ("startedAt", "started_at"),
            ("finishedAt", "finished_at"),
            ("serverId", "server_id"),
        ):
            value = deployment_item.get(key_name)
            if value is not None:
                deployment_summary[output_key] = cast(JsonValue, value)
        rendered_deployments.append(deployment_summary)

    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "target_type": resolved_target_type,
        "target_id": resolved_target_id,
        "target_name": resolved_target_name,
        "deployments": cast(JsonValue, rendered_deployments),
        "streaming_supported": False,
        "note": "Deployment metadata includes log_path for each run. Direct streaming requires authenticated Dokploy websocket sessions.",
    }
    _emit_payload(payload, json_output=json_output)


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
@click.option("--json-output", is_flag=True, default=False)
def dokploy_reconcile(
    stack_file: Path,
    source_file: Path,
    env_file: Path | None,
    context_filter: str | None,
    instance_filter: str | None,
    apply: bool,
    json_output: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    _loaded_stack = _load_stack(stack_file_path)
    source_file_path = _resolve_dokploy_source_file(repo_root, source_file)
    source_of_truth = _load_dokploy_source_of_truth(source_file_path)
    _env_file_path, environment_values = _load_environment(repo_root, env_file)
    host, token = _read_dokploy_config(environment_values)

    results: list[JsonObject] = []
    matched_targets = [
        target
        for target in source_of_truth.targets
        if _target_matches_filters(target, context_filter=context_filter, instance_filter=instance_filter)
    ]
    if not matched_targets:
        raise click.ClickException("No source-of-truth targets matched the requested filters.")

    for target in matched_targets:
        context_name = target.context
        instance_name = target.instance
        target_type = target.target_type

        resolved_target_id = target.target_id.strip()
        resolved_target_name = target.target_name.strip() or f"{context_name}-{instance_name}"

        if not resolved_target_id:
            if target_type == "compose":
                resolved_target_id, resolved_target_name = _resolve_dokploy_compose_id(
                    host=host,
                    token=token,
                    context_name=context_name,
                    instance_name=instance_name,
                    environment_values=environment_values,
                )
            else:
                resolved_target_id, resolved_target_name = _resolve_dokploy_application_id(
                    host=host,
                    token=token,
                    context_name=context_name,
                    instance_name=instance_name,
                    environment_values=environment_values,
                )

        target_payload = _fetch_dokploy_target_payload(
            host=host,
            token=token,
            target_type=target_type,
            target_id=resolved_target_id,
        )

        current_target_name = str(target_payload.get("name") or resolved_target_name)
        current_domains = _normalize_domains(cast(JsonValue, target_payload.get("domains")))
        desired_domains = [domain for domain in target.domains if domain]
        missing_domains = [domain for domain in desired_domains if domain not in current_domains]
        unexpected_domains = [domain for domain in current_domains if domain not in desired_domains]

        desired_branch = target.git_branch.strip()
        current_branch = ""
        branch_needs_update = False
        branch_updated = False
        current_auto_deploy: bool | None = None
        desired_auto_deploy = target.auto_deploy
        auto_deploy_needs_update = False
        auto_deploy_updated = False
        env_map = _parse_dokploy_env_text(str(target_payload.get("env") or ""))
        desired_env = {key: value for key, value in target.env.items() if key}
        env_needs_update_keys: list[str] = []
        env_updated = False
        if target_type == "compose":
            current_branch = str(target_payload.get("customGitBranch") or "").strip()
            if desired_branch:
                branch_needs_update = current_branch != desired_branch

            raw_auto_deploy = target_payload.get("autoDeploy")
            if isinstance(raw_auto_deploy, bool):
                current_auto_deploy = raw_auto_deploy
            if desired_auto_deploy is not None and current_auto_deploy is not None:
                auto_deploy_needs_update = current_auto_deploy != desired_auto_deploy

            compose_update_payload: JsonObject = {"composeId": resolved_target_id}
            if branch_needs_update:
                compose_update_payload["customGitBranch"] = desired_branch
            if auto_deploy_needs_update and desired_auto_deploy is not None:
                compose_update_payload["autoDeploy"] = desired_auto_deploy

            if apply and len(compose_update_payload) > 1:
                _dokploy_request(
                    host=host,
                    token=token,
                    path="/api/compose.update",
                    method="POST",
                    payload=compose_update_payload,
                )

                branch_updated = branch_needs_update
                auto_deploy_updated = auto_deploy_needs_update

        for env_key, env_value in desired_env.items():
            if env_map.get(env_key) != env_value:
                env_needs_update_keys.append(env_key)
                env_map[env_key] = env_value

        if env_needs_update_keys and apply:
            _update_dokploy_target_env(
                host=host,
                token=token,
                target_type=target_type,
                target_id=resolved_target_id,
                target_payload=target_payload,
                env_text=_serialize_dokploy_env_text(env_map),
            )
            env_updated = True

        result_payload: JsonObject = {
            "context": context_name,
            "instance": instance_name,
            "target_type": target_type,
            "target_id": resolved_target_id,
            "target_name": current_target_name,
            "desired_branch": desired_branch,
            "current_branch": current_branch,
            "branch_needs_update": branch_needs_update,
            "branch_updated": branch_updated,
            "desired_auto_deploy": desired_auto_deploy,
            "current_auto_deploy": current_auto_deploy,
            "auto_deploy_needs_update": auto_deploy_needs_update,
            "auto_deploy_updated": auto_deploy_updated,
            "desired_env_keys": cast(JsonValue, sorted(desired_env.keys())),
            "env_needs_update_keys": cast(JsonValue, env_needs_update_keys),
            "env_updated": env_updated,
            "desired_domains": cast(JsonValue, desired_domains),
            "current_domains": cast(JsonValue, current_domains),
            "missing_domains": cast(JsonValue, missing_domains),
            "unexpected_domains": cast(JsonValue, unexpected_domains),
        }
        results.append(result_payload)

    payload: JsonObject = {
        "source_file": str(source_file_path),
        "apply": apply,
        "matched_targets": len(results),
        "updated_targets": len(
            [
                item
                for item in results
                if bool(item.get("branch_updated"))
                or bool(item.get("auto_deploy_updated"))
                or bool(item.get("env_updated"))
            ]
        ),
        "targets": cast(JsonValue, results),
    }
    _emit_payload(payload, json_output=json_output)


@main.command("select")
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
def select(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None, dry_run: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    loaded_environment_details = _load_environment_with_details(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    loaded_environment = loaded_environment_details.merged_values
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"

    if dry_run:
        runtime_values = _build_runtime_env_values(
            runtime_env_file,
            loaded_stack.stack_definition,
            runtime_selection,
            loaded_environment,
        )
        existing_runtime_values = _parse_env_file(runtime_env_file) if runtime_env_file.exists() else {}
        payload: JsonObject = {
            "selected_context": context_name,
            "selected_instance": instance_name,
            "dry_run": True,
            "env_file": str(loaded_environment_details.env_file_path),
            "runtime_env_file": str(runtime_env_file),
            "runtime_env_exists": runtime_env_file.exists(),
            "runtime_env_diff": _runtime_env_diff(existing_runtime_values, runtime_values),
            "collisions": cast(
                JsonValue,
                [
                    {
                        "key": collision.key,
                        "previous_layer": collision.previous_layer,
                        "incoming_layer": collision.incoming_layer,
                    }
                    for collision in loaded_environment_details.collisions
                ],
            ),
        }
        _emit_payload(payload, json_output=False)
        return

    _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)
    runtime_env_file = _write_runtime_env_file(
        repo_root,
        loaded_stack.stack_definition,
        runtime_selection,
        loaded_environment,
    )
    click.echo(f"selected_context={context_name}")
    click.echo(f"selected_instance={instance_name}")
    click.echo(f"runtime_env_file={runtime_env_file}")
    click.echo(f"root_env_file={repo_root / '.env'}")


@main.command("up")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--build/--no-build", default=True)
@click.option("--no-cache", is_flag=True, default=False)
def up(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    build: bool,
    no_cache: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)

    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)

    runtime_env_file = _write_runtime_env_file(
        repo_root,
        loaded_stack.stack_definition,
        runtime_selection,
        loaded_environment,
    )
    _ensure_registry_auth_for_base_images(loaded_environment)
    compose_command = _compose_base_command(runtime_env_file)
    if build:
        build_command = compose_command + ["build"]
        if no_cache:
            build_command.append("--no-cache")
        _run_command(build_command)
    elif no_cache:
        raise click.ClickException("--no-cache requires --build.")
    up_command = compose_command + ["up", "-d", "--no-build"]
    _run_command(up_command)
    click.echo(f"up={runtime_selection.project_name}")


@main.command("down")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--volumes", is_flag=True, default=False)
def down(context_name: str, instance_name: str, volumes: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    compose_command = _compose_base_command(runtime_env_file)
    down_command = compose_command + ["down", "--remove-orphans"]
    if volumes:
        down_command.append("--volumes")
    _run_command(down_command)
    click.echo(f"down={context_name}-{instance_name}")


@main.command("logs")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--service", default="web", show_default=True)
@click.option("--follow/--no-follow", default=True)
@click.option("--lines", default=200, show_default=True)
def logs(context_name: str, instance_name: str, service: str, follow: bool, lines: int) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    compose_command = _compose_base_command(runtime_env_file)
    log_command = compose_command + ["logs", "--tail", str(lines)]
    if follow:
        log_command.append("-f")
    log_command.append(service)
    _run_command(log_command)


def _compose_exec(runtime_env_file: Path, container_service: str, container_command: list[str]) -> None:
    compose_command = _compose_base_command(runtime_env_file)
    _run_command(compose_command + ["exec", "-T", container_service] + container_command)


def _compose_exec_with_input(
    runtime_env_file: Path,
    container_service: str,
    container_command: list[str],
    input_text: str,
) -> None:
    compose_command = _compose_base_command(runtime_env_file)
    _run_command_with_input(compose_command + ["exec", "-T", container_service] + container_command, input_text)


def _run_with_web_temporarily_stopped(
    runtime_env_file: Path,
    operation: Callable[[], None],
    *,
    dry_run: bool,
    dry_run_commands: tuple[list[str], ...],
) -> None:
    compose_command = _compose_base_command(runtime_env_file)
    stop_web_command = compose_command + ["stop", "web"]
    up_web_command = compose_command + ["up", "-d", "web"]

    if dry_run:
        click.echo(f"$ {' '.join(stop_web_command)}")
        for command in dry_run_commands:
            click.echo(f"$ {' '.join(command)}")
        click.echo(f"$ {' '.join(up_web_command)}")
        return

    _run_command_best_effort(stop_web_command)
    try:
        operation()
    finally:
        _run_command_best_effort(up_web_command)


def _apply_admin_password_if_configured(
    runtime_env_file: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    loaded_environment: dict[str, str],
) -> None:
    admin_password = loaded_environment.get("ODOO_ADMIN_PASSWORD", "").strip()
    if not admin_password:
        return

    configured_admin_login_raw = loaded_environment.get("ODOO_ADMIN_LOGIN", "")
    configured_admin_login = configured_admin_login_raw.strip()
    if not configured_admin_login:
        click.echo("admin_password_action=skipped_missing_odoo_admin_login")
        return

    addons_path_argument = ",".join(stack_definition.addons_path)
    odoo_shell_command = [
        "/odoo/odoo-bin",
        "shell",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
    ]

    script_payload = {
        "password": admin_password,
        "login": configured_admin_login,
    }
    odoo_shell_script = textwrap.dedent("""
import json

payload = json.loads('__PAYLOAD__')
admin_user = env['res.users'].sudo().with_context(active_test=False).search(
    [('login', '=', payload['login'])],
    limit=1,
)
if not admin_user:
    raise ValueError(f"Configured admin user not found: {payload['login']}")
else:
    admin_user.with_context(no_reset_password=True).sudo().password = payload['password']
    print("admin_password_updated=true")
env.cr.commit()
""").replace("__PAYLOAD__", json.dumps(script_payload))

    _compose_exec_with_input(runtime_env_file, "script-runner", odoo_shell_command, odoo_shell_script)


def _assert_active_admin_password_is_not_default(
    runtime_env_file: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    loaded_environment: dict[str, str],
) -> None:
    configured_admin_login_raw = loaded_environment.get("ODOO_ADMIN_LOGIN", "")
    configured_admin_login = configured_admin_login_raw.strip()
    if not configured_admin_login:
        return

    addons_path_argument = ",".join(stack_definition.addons_path)
    odoo_shell_command = [
        "/odoo/odoo-bin",
        "shell",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
    ]

    script_payload = {
        "login": configured_admin_login,
    }
    odoo_shell_script = textwrap.dedent("""
import json
from odoo.exceptions import AccessDenied

payload = json.loads('__PAYLOAD__')

admin_user = env['res.users'].sudo().with_context(active_test=False).search(
    [('login', '=', payload['login'])],
    limit=1,
)
if not admin_user:
    raise ValueError(f"Configured admin user not found: {payload['login']}")
else:
    authenticated = False
    try:
        auth_info = env['res.users'].sudo().authenticate(
            {'type': 'password', 'login': payload['login'], 'password': 'admin'},
            {'interactive': False},
        )
        authenticated = bool(auth_info)
    except AccessDenied:
        authenticated = False

    if authenticated:
        raise ValueError(f"Insecure configuration: active password for {payload['login']} is 'admin'.")
    print("admin_default_password_active=false")
""").replace("__PAYLOAD__", json.dumps(script_payload))

    _compose_exec_with_input(runtime_env_file, "script-runner", odoo_shell_command, odoo_shell_script)


@main.command("build")
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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)
    runtime_env_file = _write_runtime_env_file(
        repo_root,
        loaded_stack.stack_definition,
        runtime_selection,
        loaded_environment,
    )

    _ensure_registry_auth_for_base_images(loaded_environment)
    compose_command = _compose_base_command(runtime_env_file)
    build_command = compose_command + ["build"]
    if no_cache:
        build_command.append("--no-cache")
    _run_command(build_command)
    click.echo(f"build={runtime_selection.project_name}")


@main.command("inspect")
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
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_conf_file = _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)

    inspection_payload = {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "odoo_conf_host": str(runtime_conf_file),
        "odoo_conf_container": runtime_selection.runtime_odoo_conf_path,
        "addons_path": list(loaded_stack.stack_definition.addons_path),
        "addon_repositories": list(runtime_selection.effective_addon_repositories),
        "install_modules": list(runtime_selection.effective_install_modules),
        "note": "Use this context/instance pair in PyCharm run configs and inspections.",
    }

    if json_output:
        click.echo(json.dumps(inspection_payload, indent=2))
        return

    for key, value in inspection_payload.items():
        click.echo(f"{key}={value}")


@main.command("ship")
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
    "--source-ref",
    "source_git_ref",
    default="",
    help="Git reference used to sync the Dokploy target branch before deploy. Defaults to target source_git_ref or main.",
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
    source_git_ref: str,
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Ship currently supports cm/opw contexts.")

    repo_root = _discover_repo_root(Path.cwd())
    _env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    source_of_truth = _load_dokploy_source_of_truth_if_present(repo_root)
    target_definition = None
    if source_of_truth is not None:
        target_definition = _find_dokploy_target_definition(
            source_of_truth,
            context_name=context_name,
            instance_name=instance_name,
        )
    deploy_timeout_seconds = _resolve_ship_timeout_seconds(
        timeout_override_seconds=timeout_override_seconds,
        target_definition=target_definition,
    )
    health_timeout_seconds = _resolve_ship_health_timeout_seconds(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )
    healthcheck_urls = _resolve_ship_healthcheck_urls(
        target_definition=target_definition,
        environment_values=environment_values,
    )
    should_verify_health = verify_health and wait
    ship_branch_sync_plan = _prepare_ship_branch_sync(source_git_ref, target_definition)

    if ship_branch_sync_plan is None:
        click.echo("branch_sync=false")
    else:
        click.echo("branch_sync=true")
        click.echo(f"branch_sync_target_branch={ship_branch_sync_plan.target_branch}")
        click.echo(f"branch_sync_source_ref={ship_branch_sync_plan.source_git_ref}")
        click.echo(f"branch_sync_source_commit={ship_branch_sync_plan.source_commit}")
        click.echo(
            f"branch_sync_remote_before={ship_branch_sync_plan.remote_branch_commit_before or 'missing'}"
        )
        click.echo(f"branch_sync_update_required={str(ship_branch_sync_plan.branch_update_required).lower()}")

    _run_required_gates(
        context_name=context_name,
        target_definition=target_definition,
        dry_run=dry_run,
        skip_gate=skip_gate,
    )
    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    try:
        host, token = _read_dokploy_config(environment_values)
    except click.ClickException as error:
        if dry_run:
            target_name = _resolve_dokploy_compose_name(context_name, instance_name, environment_values)
            if ship_mode == "application":
                target_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
            click.echo(f"ship_mode=dokploy-{ship_mode}-api")
            click.echo(f"target_name={target_name}")
            click.echo(f"dry_run_note={error.message}")
            click.echo(f"deploy_timeout_seconds={deploy_timeout_seconds}")
            click.echo(f"verify_health={str(should_verify_health).lower()}")
            if ship_branch_sync_plan is not None:
                click.echo("branch_sync_applied=false")
            if should_verify_health:
                click.echo(f"health_timeout_seconds={health_timeout_seconds}")
                for healthcheck_url in healthcheck_urls:
                    click.echo(f"healthcheck_url={healthcheck_url}")
            return
        raise

    (
        selected_target_type,
        selected_target_id,
        selected_target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = _resolve_dokploy_target(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        ship_mode=ship_mode,
    )

    if not selected_target_type:
        messages = ["No Dokploy deployment target resolved."]
        if compose_resolution_error is not None:
            messages.append(f"compose_error={compose_resolution_error.message}")
        if app_resolution_error is not None:
            messages.append(f"application_error={app_resolution_error.message}")
        raise click.ClickException(" ".join(messages))

    before_key = ""
    if selected_target_type == "compose":
        latest_before = _latest_deployment_for_compose(host, token, selected_target_id)
        before_key = _deployment_key(latest_before or {})
    else:
        latest_before = _latest_deployment_for_application(host, token, selected_target_id)
        before_key = _deployment_key(latest_before or {})

    branch_sync_applied = False
    if ship_branch_sync_plan is not None:
        if dry_run:
            click.echo("branch_sync_applied=false")
        else:
            _apply_ship_branch_sync(ship_branch_sync_plan)
            branch_sync_applied = ship_branch_sync_plan.branch_update_required
            click.echo(f"branch_sync_applied={str(branch_sync_applied).lower()}")

    if selected_target_type == "compose":
        compose_endpoint = "/api/compose.redeploy" if no_cache else "/api/compose.deploy"
        compose_payload: JsonObject = {"composeId": selected_target_id}
        if no_cache:
            compose_payload["title"] = "Manual redeploy (no-cache requested)"

        click.echo("ship_mode=dokploy-compose-api")
        click.echo(f"compose_name={selected_target_name}")
        click.echo(f"compose_id={selected_target_id}")
        click.echo(f"deploy_action={'redeploy' if no_cache else 'deploy'}")
        click.echo(f"no_cache={str(no_cache).lower()}")
        click.echo(f"deploy_timeout_seconds={deploy_timeout_seconds}")
        click.echo(f"verify_health={str(should_verify_health).lower()}")
        if should_verify_health:
            click.echo(f"health_timeout_seconds={health_timeout_seconds}")
            for healthcheck_url in healthcheck_urls:
                click.echo(f"healthcheck_url={healthcheck_url}")
        if dry_run:
            return

        _dokploy_request(
            host=host,
            token=token,
            path=compose_endpoint,
            method="POST",
            payload=compose_payload,
        )
        click.echo("deploy_triggered=true")
        if not wait:
            return
        result = _wait_for_dokploy_compose_deployment(
            host=host,
            token=token,
            compose_id=selected_target_id,
            before_key=before_key,
            timeout_seconds=deploy_timeout_seconds,
        )
        click.echo(result)
        if should_verify_health:
            if not healthcheck_urls:
                click.echo("healthcheck_result=skipped-no-target-domain")
            else:
                _verify_ship_healthchecks(urls=healthcheck_urls, timeout_seconds=health_timeout_seconds)
        return

    application_endpoint = "/api/application.redeploy" if no_cache else "/api/application.deploy"
    application_payload: JsonObject = {"applicationId": selected_target_id}
    if no_cache:
        application_payload["title"] = "Manual redeploy (no-cache requested)"

    click.echo(f"ship_mode=dokploy-api")
    click.echo(f"app_name={selected_target_name}")
    click.echo(f"application_id={selected_target_id}")
    click.echo(f"deploy_action={'redeploy' if no_cache else 'deploy'}")
    click.echo(f"no_cache={str(no_cache).lower()}")
    click.echo(f"deploy_timeout_seconds={deploy_timeout_seconds}")
    click.echo(f"verify_health={str(should_verify_health).lower()}")
    if should_verify_health:
        click.echo(f"health_timeout_seconds={health_timeout_seconds}")
        for healthcheck_url in healthcheck_urls:
            click.echo(f"healthcheck_url={healthcheck_url}")
    if dry_run:
        return

    _dokploy_request(
        host=host,
        token=token,
        path=application_endpoint,
        method="POST",
        payload=application_payload,
    )
    click.echo("deploy_triggered=true")
    if not wait:
        return
    result = _wait_for_dokploy_deployment(
        host=host,
        token=token,
        application_id=selected_target_id,
        before_key=before_key,
        timeout_seconds=deploy_timeout_seconds,
    )
    click.echo(result)
    if should_verify_health:
        if not healthcheck_urls:
            click.echo("healthcheck_result=skipped-no-target-domain")
        else:
            _verify_ship_healthchecks(urls=healthcheck_urls, timeout_seconds=health_timeout_seconds)


@main.command("rollback")
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
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Rollback currently supports cm/opw contexts.")

    repo_root = _discover_repo_root(Path.cwd())
    _env_file_path, environment_values = _load_environment(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    if ship_mode == "compose":
        raise click.ClickException("Rollback in compose ship mode is not supported yet. Use Dokploy UI rollback controls.")
    try:
        host, token = _read_dokploy_config(environment_values)
    except click.ClickException as error:
        if dry_run:
            app_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
            click.echo(f"app_name={app_name}")
            click.echo(f"dry_run_note={error.message}")
            return
        raise
    application_id, app_name = _resolve_dokploy_application_id(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
    )

    deployment_payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = _extract_deployments(deployment_payload)
    discovered_rollback_ids = _collect_rollback_ids(deployments)

    click.echo(f"app_name={app_name}")
    click.echo(f"application_id={application_id}")

    if list_only:
        click.echo(json.dumps({"rollback_ids": discovered_rollback_ids}, indent=2))
        return

    selected_rollback_id = rollback_id.strip()
    if not selected_rollback_id:
        if not discovered_rollback_ids:
            raise click.ClickException(
                "No rollback ids discovered for this application. Pass --rollback-id explicitly or run --list."
            )
        selected_rollback_id = discovered_rollback_ids[0]

    latest_before = _latest_deployment_for_application(host, token, application_id)
    before_key = _deployment_key(latest_before or {})

    click.echo(f"rollback_id={selected_rollback_id}")
    if dry_run:
        return

    _dokploy_request(
        host=host,
        token=token,
        path="/api/rollback.rollback",
        method="POST",
        payload={"rollbackId": selected_rollback_id},
    )
    click.echo("rollback_triggered=true")
    if not wait:
        return
    result = _wait_for_dokploy_deployment(
        host=host,
        token=token,
        application_id=application_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )
    click.echo(result)


@main.command("init")
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
def init(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None, dry_run: bool) -> None:
    _run_init_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
    )


@main.command("openupgrade")
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
    _run_openupgrade_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
    )


@main.command("update")
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
    _run_update_workflow(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
