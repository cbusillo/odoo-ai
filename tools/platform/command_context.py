from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import click

from .models import LoadedStack, RuntimeSelection, StackDefinition


@dataclass(frozen=True)
class RuntimeCommandContext:
    loaded_stack: LoadedStack
    runtime_selection: RuntimeSelection
    env_file_path: Path
    environment_values: dict[str, str]
    runtime_env_file: Path


def resolve_stack_file_path(repo_root: Path, stack_file: Path) -> Path:
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")
    return stack_file_path


def load_runtime_command_context(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
) -> RuntimeCommandContext:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = resolve_stack_file_path(repo_root, stack_file)
    loaded_stack = load_stack_fn(stack_file_path)
    runtime_selection = resolve_runtime_selection_fn(loaded_stack.stack_definition, context_name, instance_name)
    env_file_path, environment_values = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    return RuntimeCommandContext(
        loaded_stack=loaded_stack,
        runtime_selection=runtime_selection,
        env_file_path=env_file_path,
        environment_values=environment_values,
        runtime_env_file=runtime_env_file,
    )
