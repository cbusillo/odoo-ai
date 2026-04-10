from collections.abc import Callable
from pathlib import Path

from . import command_context
from .models import JsonObject, LoadedStack, RuntimeSelection, StackDefinition


def execute_export_artifact_identity(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    git_reference: str,
    enterprise_base_digest: str,
    image_repository: str,
    image_digest: str,
    image_tags: tuple[str, ...],
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_local_git_commit_fn: Callable[[str], str],
    build_artifact_identity_manifest_fn: Callable[..., object],
    emit_payload_fn: Callable[[JsonObject], None],
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
    resolved_commit = resolve_local_git_commit_fn(git_reference)
    artifact_identity_manifest = build_artifact_identity_manifest_fn(
        odoo_ai_commit=resolved_commit,
        enterprise_base_digest=enterprise_base_digest,
        image_repository=image_repository,
        image_digest=image_digest,
        image_tags=image_tags,
        runtime_selection=runtime_command_context.runtime_selection,
        source_environment=runtime_command_context.environment_values,
    )
    emit_payload_fn(artifact_identity_manifest.model_dump(mode="json"))
