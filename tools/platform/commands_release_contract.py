import click

from collections.abc import Callable
from pathlib import Path

from . import command_context
from .models import JsonObject, LoadedStack, ReleaseStatus, RuntimeSelection, StackDefinition


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


def execute_handoff_artifact_identity(
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
    invoke_control_plane_artifact_handoff_fn: Callable[..., None],
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
    invoke_control_plane_artifact_handoff_fn(manifest=artifact_identity_manifest)


def _parse_metadata_items(*, items: tuple[str, ...], option_name: str) -> dict[str, str]:
    parsed_items: dict[str, str] = {}
    for raw_item in items:
        key_name, separator, value = raw_item.partition("=")
        cleaned_key_name = key_name.strip()
        if separator != "=" or not cleaned_key_name:
            raise click.ClickException(f"{option_name} entries must use <key>=<value>: {raw_item}")
        parsed_items[cleaned_key_name] = value.strip()
    return parsed_items


def _resolve_healthcheck_status(*, explicit_status: ReleaseStatus | None, should_plan_verification: bool) -> ReleaseStatus:
    if explicit_status is not None:
        return explicit_status
    return "pending" if should_plan_verification else "skipped"


def _resolve_backup_gate_status(*, explicit_status: ReleaseStatus | None, backup_gate_required: bool) -> ReleaseStatus:
    if explicit_status is not None:
        return explicit_status
    return "pending" if backup_gate_required else "skipped"


def _resolve_post_deploy_update_status(
    *,
    explicit_status: ReleaseStatus | None,
    wait: bool,
    target_type: str,
) -> ReleaseStatus:
    if explicit_status is not None:
        return explicit_status
    if wait and target_type == "compose":
        return "pending"
    return "skipped"


def _resolve_deploy_mode(*, configured_ship_mode: str, target_type: str) -> str:
    selected_mode = configured_ship_mode if configured_ship_mode != "auto" else target_type
    return f"dokploy-{selected_mode}-api"


def execute_export_promotion_record(
    *,
    context_name: str,
    from_instance_name: str,
    to_instance_name: str,
    env_file: Path | None,
    artifact_id: str,
    wait: bool,
    verify_health: bool,
    health_timeout_override_seconds: int | None,
    verify_source_health: bool,
    source_health_timeout_override_seconds: int | None,
    deployment_id: str,
    deploy_started_at: str,
    deploy_finished_at: str,
    deploy_status: ReleaseStatus,
    source_health_status: ReleaseStatus | None,
    backup_gate_status: ReleaseStatus | None,
    backup_evidence_items: tuple[str, ...],
    post_deploy_update_status: ReleaseStatus | None,
    post_deploy_update_detail: str,
    destination_health_status: ReleaseStatus | None,
    assert_promote_path_allowed_fn: Callable[..., None],
    discover_repo_root_fn: Callable[[Path], Path],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], object | None],
    find_dokploy_target_definition_fn: Callable[..., object | None],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    build_compatibility_promotion_record_fn: Callable[..., object],
    emit_payload_fn: Callable[[JsonObject], None],
) -> None:
    assert_promote_path_allowed_fn(
        from_instance_name=from_instance_name,
        to_instance_name=to_instance_name,
    )
    repo_root = discover_repo_root_fn(Path.cwd())
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(repo_root)
    if source_of_truth is None:
        raise click.ClickException("Promotion record export requires platform/dokploy.toml with target definitions.")

    source_target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=from_instance_name,
    )
    if source_target_definition is None:
        raise click.ClickException(f"No Dokploy target definition found for {context_name}/{from_instance_name}.")

    destination_target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=to_instance_name,
    )
    if destination_target_definition is None:
        raise click.ClickException(f"No Dokploy target definition found for {context_name}/{to_instance_name}.")

    _source_env_file_path, source_environment_values = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=from_instance_name,
        collision_mode="error",
    )
    _destination_env_file_path, destination_environment_values = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=to_instance_name,
        collision_mode="error",
    )

    source_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=source_health_timeout_override_seconds,
        target_definition=source_target_definition,
    )
    destination_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=destination_target_definition,
    )
    source_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
        target_definition=source_target_definition,
        environment_values=source_environment_values,
    )
    destination_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
        target_definition=destination_target_definition,
        environment_values=destination_environment_values,
    )
    configured_ship_mode = resolve_dokploy_ship_mode_fn(
        context_name,
        to_instance_name,
        destination_environment_values,
    )
    deploy_mode = _resolve_deploy_mode(
        configured_ship_mode=configured_ship_mode,
        target_type=destination_target_definition.target_type,
    )
    backup_gate_required = to_instance_name.strip().lower() == "prod"

    try:
        promotion_record = build_compatibility_promotion_record_fn(
            artifact_id=artifact_id,
            context_name=context_name,
            from_instance_name=from_instance_name,
            to_instance_name=to_instance_name,
            destination_target_definition=destination_target_definition,
            deploy_mode=deploy_mode,
            deployment_id=deployment_id,
            deploy_status=deploy_status,
            deploy_started_at=deploy_started_at,
            deploy_finished_at=deploy_finished_at,
            source_health_urls=source_healthcheck_urls,
            source_health_timeout_seconds=source_health_timeout_seconds,
            source_health_status=_resolve_healthcheck_status(
                explicit_status=source_health_status,
                should_plan_verification=verify_source_health,
            ),
            backup_gate_required=backup_gate_required,
            backup_gate_status=_resolve_backup_gate_status(
                explicit_status=backup_gate_status,
                backup_gate_required=backup_gate_required,
            ),
            backup_gate_evidence=_parse_metadata_items(
                items=backup_evidence_items,
                option_name="--backup-evidence",
            ),
            post_deploy_update_status=_resolve_post_deploy_update_status(
                explicit_status=post_deploy_update_status,
                wait=wait,
                target_type=destination_target_definition.target_type,
            ),
            post_deploy_update_detail=post_deploy_update_detail,
            destination_health_urls=destination_healthcheck_urls,
            destination_health_timeout_seconds=destination_health_timeout_seconds,
            destination_health_status=_resolve_healthcheck_status(
                explicit_status=destination_health_status,
                should_plan_verification=verify_health and wait,
            ),
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    emit_payload_fn(promotion_record.model_dump(mode="json"))


def execute_export_ship_request(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    source_git_ref: str,
    wait: bool,
    timeout_override_seconds: int | None,
    verify_health: bool,
    health_timeout_override_seconds: int | None,
    dry_run: bool,
    no_cache: bool,
    allow_dirty: bool,
    default_source_git_ref: str,
    discover_repo_root_fn: Callable[[Path], Path],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], object | None],
    find_dokploy_target_definition_fn: Callable[..., object | None],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    build_compatibility_ship_request_fn: Callable[..., object],
    emit_payload_fn: Callable[[JsonObject], None],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(repo_root)
    if source_of_truth is None:
        raise click.ClickException("Ship request export requires platform/dokploy.toml with target definitions.")

    target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise click.ClickException(f"No Dokploy target definition found for {context_name}/{instance_name}.")

    environment_values: dict[str, str] = {}
    try:
        _env_file_path, environment_values = load_environment_fn(
            repo_root,
            env_file,
            context_name=context_name,
            instance_name=instance_name,
            collision_mode="error",
        )
    except click.ClickException:
        if verify_health and wait:
            raise

    resolved_source_git_ref = source_git_ref.strip() or target_definition.source_git_ref.strip() or default_source_git_ref
    destination_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )
    destination_healthcheck_urls: tuple[str, ...] = ()
    if environment_values:
        destination_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
            target_definition=target_definition,
            environment_values=environment_values,
        )
    configured_ship_mode = "auto"
    if environment_values:
        configured_ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    deploy_mode = _resolve_deploy_mode(
        configured_ship_mode=configured_ship_mode,
        target_type=target_definition.target_type,
    )

    try:
        ship_request = build_compatibility_ship_request_fn(
            context_name=context_name,
            instance_name=instance_name,
            source_git_ref=resolved_source_git_ref,
            target_name=target_definition.target_name.strip() or f"{context_name}-{instance_name}",
            target_type=target_definition.target_type,
            deploy_mode=deploy_mode,
            wait=wait,
            timeout_seconds=timeout_override_seconds,
            verify_health=verify_health,
            health_timeout_seconds=destination_health_timeout_seconds,
            dry_run=dry_run,
            no_cache=no_cache,
            allow_dirty=allow_dirty,
            destination_health_urls=destination_healthcheck_urls,
            destination_health_timeout_seconds=destination_health_timeout_seconds,
            destination_health_status="pending" if verify_health and wait else "skipped",
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    emit_payload_fn(ship_request.model_dump(mode="json"))


def execute_delegate_ship(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    source_git_ref: str,
    wait: bool,
    timeout_override_seconds: int | None,
    verify_health: bool,
    health_timeout_override_seconds: int | None,
    dry_run: bool,
    no_cache: bool,
    allow_dirty: bool,
    default_source_git_ref: str,
    discover_repo_root_fn: Callable[[Path], Path],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], object | None],
    find_dokploy_target_definition_fn: Callable[..., object | None],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    run_required_gates_fn: Callable[..., None],
    build_compatibility_ship_request_fn: Callable[..., object],
    invoke_control_plane_ship_fn: Callable[..., None],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(repo_root)
    if source_of_truth is None:
        raise click.ClickException("Ship delegation requires platform/dokploy.toml with target definitions.")

    target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise click.ClickException(f"No Dokploy target definition found for {context_name}/{instance_name}.")

    if not dry_run:
        run_required_gates_fn(
            context_name=context_name,
            target_definition=target_definition,
            dry_run=False,
            skip_gate=False,
        )

    environment_values: dict[str, str] = {}
    try:
        _env_file_path, environment_values = load_environment_fn(
            repo_root,
            env_file,
            context_name=context_name,
            instance_name=instance_name,
            collision_mode="error",
        )
    except click.ClickException:
        if verify_health and wait:
            raise

    resolved_source_git_ref = source_git_ref.strip() or target_definition.source_git_ref.strip() or default_source_git_ref
    destination_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )
    destination_healthcheck_urls: tuple[str, ...] = ()
    if environment_values:
        destination_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
            target_definition=target_definition,
            environment_values=environment_values,
        )
    configured_ship_mode = "auto"
    if environment_values:
        configured_ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    deploy_mode = _resolve_deploy_mode(
        configured_ship_mode=configured_ship_mode,
        target_type=target_definition.target_type,
    )

    try:
        ship_request = build_compatibility_ship_request_fn(
            context_name=context_name,
            instance_name=instance_name,
            source_git_ref=resolved_source_git_ref,
            target_name=target_definition.target_name.strip() or f"{context_name}-{instance_name}",
            target_type=target_definition.target_type,
            deploy_mode=deploy_mode,
            wait=wait,
            timeout_seconds=timeout_override_seconds,
            verify_health=verify_health,
            health_timeout_seconds=destination_health_timeout_seconds,
            dry_run=dry_run,
            no_cache=no_cache,
            allow_dirty=allow_dirty,
            destination_health_urls=destination_healthcheck_urls,
            destination_health_timeout_seconds=destination_health_timeout_seconds,
            destination_health_status="pending" if verify_health and wait else "skipped",
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    invoke_control_plane_ship_fn(repo_root=repo_root, env_file=env_file, request=ship_request)
