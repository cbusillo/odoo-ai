from __future__ import annotations

import os
import tomllib
from pathlib import Path

import click
from pydantic import ValidationError

from tools import environment_files

from .models import (
    DokploySourceOfTruth,
    EnvironmentCollision,
    EnvironmentLayer,
    LoadedEnvironment,
    LoadedStack,
    PlatformSecretsDefinition,
    StackDefinition,
)

ENV_COLLISION_MODE_ENV_KEY = "PLATFORM_ENV_COLLISION_MODE"
VALID_ENV_COLLISION_MODES = ("warn", "error", "ignore")


def discover_repo_root(start_directory: Path) -> Path:
    return environment_files.discover_repo_root(start_directory)


def parse_env_file(env_file_path: Path) -> dict[str, str]:
    return environment_files.parse_env_file(env_file_path)


def resolve_platform_secrets_file(repo_root: Path) -> Path:
    return repo_root / "platform" / "secrets.toml"


def normalize_secret_env_values(raw_values: dict[str, str | int | float | bool]) -> dict[str, str]:
    normalized_values: dict[str, str] = {}
    for key, value in raw_values.items():
        normalized_values[str(key)] = str(value)
    return normalized_values


def load_platform_secrets_definition(repo_root: Path) -> PlatformSecretsDefinition | None:
    secrets_file = resolve_platform_secrets_file(repo_root)
    if not secrets_file.exists():
        return None
    try:
        payload = tomllib.loads(secrets_file.read_text(encoding="utf-8"))
        return PlatformSecretsDefinition.model_validate(payload)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        raise click.ClickException(f"Invalid platform secrets file {secrets_file}: {exc}") from exc


def resolve_env_collision_mode(collision_mode: str | None) -> str:
    if collision_mode is not None:
        normalized_mode = collision_mode.strip().lower()
    else:
        env_mode = os.environ.get(ENV_COLLISION_MODE_ENV_KEY, "")
        normalized_mode = env_mode.strip().lower() if env_mode else "warn"
    if normalized_mode not in VALID_ENV_COLLISION_MODES:
        valid_modes = ", ".join(VALID_ENV_COLLISION_MODES)
        raise click.ClickException(f"Invalid collision mode '{normalized_mode}'. Expected one of: {valid_modes}.")
    return normalized_mode


def build_environment_layers(
    *,
    repo_root: Path,
    env_file_path: Path,
    context_name: str | None,
    instance_name: str | None,
) -> list[EnvironmentLayer]:
    environment_layers: list[EnvironmentLayer] = [
        EnvironmentLayer(
            name=f"env-file:{env_file_path}",
            values=parse_env_file(env_file_path),
        ),
    ]

    environment_layers.extend(
        build_platform_secret_layers(
            repo_root=repo_root,
            context_name=context_name,
            instance_name=instance_name,
        )
    )
    return environment_layers


def build_platform_secret_layers(
    *,
    repo_root: Path,
    context_name: str | None,
    instance_name: str | None,
) -> list[EnvironmentLayer]:
    environment_layers: list[EnvironmentLayer] = []

    platform_secrets = load_platform_secrets_definition(repo_root)
    if platform_secrets is None:
        return environment_layers

    shared_values = normalize_secret_env_values(platform_secrets.shared)
    if shared_values:
        environment_layers.append(EnvironmentLayer(name="secrets.shared", values=shared_values))

    if context_name is None:
        return environment_layers

    context_overrides = platform_secrets.contexts.get(context_name)
    if context_overrides is None:
        return environment_layers

    context_values = normalize_secret_env_values(context_overrides.shared)
    if context_values:
        environment_layers.append(EnvironmentLayer(name=f"secrets.contexts.{context_name}.shared", values=context_values))

    if instance_name is None:
        return environment_layers

    instance_overrides = context_overrides.instances.get(instance_name)
    if instance_overrides is None:
        return environment_layers

    instance_values = normalize_secret_env_values(instance_overrides.env)
    if instance_values:
        environment_layers.append(
            EnvironmentLayer(
                name=f"secrets.contexts.{context_name}.instances.{instance_name}.env",
                values=instance_values,
            )
        )

    return environment_layers


def load_secret_environment(
    repo_root: Path,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> dict[str, str]:
    secret_layers = build_platform_secret_layers(
        repo_root=repo_root,
        context_name=context_name,
        instance_name=instance_name,
    )
    normalized_collision_mode = resolve_env_collision_mode(collision_mode)
    merged_values, _source_by_key, collisions = merge_environment_layers(secret_layers)
    handle_environment_collisions(collisions, normalized_collision_mode)
    return merged_values


def merge_environment_layers(
    environment_layers: list[EnvironmentLayer],
) -> tuple[dict[str, str], dict[str, str], tuple[EnvironmentCollision, ...]]:
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


def handle_environment_collisions(collisions: tuple[EnvironmentCollision, ...], collision_mode: str) -> None:
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


def load_environment_with_details(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> LoadedEnvironment:
    env_file_path = env_file if env_file is not None else resolve_default_env_file(repo_root)
    if not env_file_path.is_absolute():
        env_file_path = repo_root / env_file_path
    if not env_file_path.exists():
        raise click.ClickException(f"Env file not found: {env_file_path}")
    environment_layers = build_environment_layers(
        repo_root=repo_root,
        env_file_path=env_file_path,
        context_name=context_name,
        instance_name=instance_name,
    )
    normalized_collision_mode = resolve_env_collision_mode(collision_mode)
    merged_values, source_by_key, collisions = merge_environment_layers(environment_layers)
    handle_environment_collisions(collisions, normalized_collision_mode)
    return LoadedEnvironment(
        env_file_path=env_file_path,
        merged_values=merged_values,
        source_by_key=source_by_key,
        collisions=collisions,
    )


def load_environment(
    repo_root: Path,
    env_file: Path | None,
    *,
    context_name: str | None = None,
    instance_name: str | None = None,
    collision_mode: str | None = None,
) -> tuple[Path, dict[str, str]]:
    loaded_environment = load_environment_with_details(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode=collision_mode,
    )
    return loaded_environment.env_file_path, loaded_environment.merged_values


def load_stack(stack_file_path: Path) -> LoadedStack:
    try:
        payload = tomllib.loads(stack_file_path.read_text(encoding="utf-8"))
        stack_definition = StackDefinition.model_validate(payload)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        raise click.ClickException(f"Invalid stack file {stack_file_path}: {exc}") from exc
    return LoadedStack(stack_definition=stack_definition, stack_file_path=stack_file_path)


def load_dokploy_source_of_truth(source_file_path: Path) -> DokploySourceOfTruth:
    try:
        payload = tomllib.loads(source_file_path.read_text(encoding="utf-8"))
        return DokploySourceOfTruth.model_validate(payload)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        raise click.ClickException(f"Invalid dokploy source-of-truth file {source_file_path}: {exc}") from exc


def resolve_default_env_file(repo_root: Path) -> Path:
    root_env = repo_root / ".env"
    if root_env.exists():
        return root_env
    platform_env = repo_root / "platform" / ".env"
    if platform_env.exists():
        return platform_env
    raise click.ClickException(
        "Missing environment file. Create .env at repository root or platform/.env, or pass --env-file explicitly."
    )


def resolve_stack_runtime_scope(stack_name: str) -> tuple[str, str] | None:
    """Map stack names (``<context>`` or ``<context>-<instance>``) to scope."""
    normalized_stack_name = stack_name.strip().lower()
    if not normalized_stack_name:
        return None
    stack_segments = normalized_stack_name.split("-")
    if len(stack_segments) == 1:
        return normalized_stack_name, "local"
    if len(stack_segments) == 2 and stack_segments[1] in {"local", "dev", "testing", "prod"}:
        return stack_segments[0], stack_segments[1]
    return None


def runtime_env_file_for_scope(repo_root: Path, context_name: str, instance_name: str) -> Path:
    return repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"


def default_local_state_path(
    *,
    repo_root: Path,
    stack_name: str | None = None,
    project_name: str | None = None,
) -> Path:
    normalized_stack_name = (stack_name or "").strip().lower()
    runtime_scope = resolve_stack_runtime_scope(normalized_stack_name) if normalized_stack_name else None
    if runtime_scope is not None:
        context_name, instance_name = runtime_scope
        return repo_root / ".platform" / "state" / f"{context_name}-{instance_name}"
    if normalized_stack_name:
        return repo_root / ".platform" / "state" / normalized_stack_name

    normalized_project_name = (project_name or "").strip().lower()
    if normalized_project_name.startswith("odoo-"):
        normalized_project_name = normalized_project_name[5:]
    runtime_scope = resolve_stack_runtime_scope(normalized_project_name) if normalized_project_name else None
    if runtime_scope is not None:
        context_name, instance_name = runtime_scope
        return repo_root / ".platform" / "state" / f"{context_name}-{instance_name}"
    if normalized_project_name:
        return repo_root / ".platform" / "state" / normalized_project_name
    return repo_root / ".platform" / "state" / "odoo"


def resolve_stack_runtime_env_file(repo_root: Path, stack_name: str) -> Path | None:
    runtime_scope = resolve_stack_runtime_scope(stack_name)
    if runtime_scope is None:
        return None
    context_name, instance_name = runtime_scope
    runtime_env_file = runtime_env_file_for_scope(repo_root, context_name, instance_name)
    if runtime_env_file.exists():
        return runtime_env_file.resolve()
    return None


def resolve_stack_env_file(
    *,
    repo_root: Path,
    stack_name: str,
    explicit_env_file: Path | None,
    require_runtime_env: bool,
) -> Path:
    if explicit_env_file is not None:
        resolved_env_file = explicit_env_file if explicit_env_file.is_absolute() else (repo_root / explicit_env_file)
        if not resolved_env_file.exists():
            raise click.ClickException(f"Env file not found: {resolved_env_file}")
        return resolved_env_file.resolve()

    runtime_scope = resolve_stack_runtime_scope(stack_name)
    runtime_env_file = resolve_stack_runtime_env_file(repo_root, stack_name)
    if runtime_env_file is not None:
        return runtime_env_file

    if require_runtime_env:
        if runtime_scope is None:
            raise click.ClickException(
                f"Unable to derive runtime scope from stack '{stack_name}'. "
                "Use --env-file explicitly or pass a stack name like '<context>-<instance>'."
            )
        context_name, instance_name = runtime_scope
        expected_runtime_env_file = runtime_env_file_for_scope(repo_root, context_name, instance_name)
        raise click.ClickException(
            f"Runtime env file not found: {expected_runtime_env_file}. "
            f"Run 'uv run platform select --context {context_name} --instance {instance_name}' first."
        )

    return resolve_default_env_file(repo_root).resolve()
