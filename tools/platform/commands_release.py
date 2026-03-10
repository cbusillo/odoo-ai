from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import click

from .models import DokploySourceOfTruth, DokployTargetDefinition, JsonObject, ShipBranchSyncPlan

SUPPORTED_RELEASE_CONTEXTS = frozenset({"cm", "opw"})


@dataclass(frozen=True)
class RuntimeEnvironment:
    repo_root: Path
    environment_values: dict[str, str]


def _assert_release_context_supported(*, context_name: str, operation_name: str) -> None:
    if context_name in SUPPORTED_RELEASE_CONTEXTS:
        return
    supported_contexts = "/".join(sorted(SUPPORTED_RELEASE_CONTEXTS))
    raise click.ClickException(f"{operation_name} currently supports {supported_contexts} contexts.")


def _load_runtime_environment(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
) -> RuntimeEnvironment:
    repo_root = discover_repo_root_fn(Path.cwd())
    _env_file_path, environment_values = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode="error",
    )
    return RuntimeEnvironment(repo_root=repo_root, environment_values=environment_values)


def _echo_healthcheck_plan(
    *,
    should_verify_health: bool,
    health_timeout_seconds: int,
    healthcheck_urls: tuple[str, ...],
    echo_fn: Callable[[str], None],
) -> None:
    if not should_verify_health:
        return
    echo_fn(f"health_timeout_seconds={health_timeout_seconds}")
    for healthcheck_url in healthcheck_urls:
        echo_fn(f"healthcheck_url={healthcheck_url}")


def _emit_deploy_plan(
    *,
    target_mode: str,
    target_label_key: str,
    target_label_value: str,
    target_id_key: str,
    target_id_value: str,
    no_cache: bool,
    deploy_timeout_seconds: int,
    should_verify_health: bool,
    health_timeout_seconds: int,
    healthcheck_urls: tuple[str, ...],
    echo_fn: Callable[[str], None],
) -> None:
    echo_fn(f"ship_mode={target_mode}")
    echo_fn(f"{target_label_key}={target_label_value}")
    echo_fn(f"{target_id_key}={target_id_value}")
    echo_fn(f"deploy_action={'redeploy' if no_cache else 'deploy'}")
    echo_fn(f"no_cache={str(no_cache).lower()}")
    echo_fn(f"deploy_timeout_seconds={deploy_timeout_seconds}")
    echo_fn(f"verify_health={str(should_verify_health).lower()}")
    _echo_healthcheck_plan(
        should_verify_health=should_verify_health,
        health_timeout_seconds=health_timeout_seconds,
        healthcheck_urls=healthcheck_urls,
        echo_fn=echo_fn,
    )


def _assert_clean_working_tree(
    *,
    allow_dirty: bool,
    check_dirty_working_tree_fn: Callable[[], tuple[str, ...]] | None,
) -> None:
    if allow_dirty or check_dirty_working_tree_fn is None:
        return
    dirty_tracked_files = tuple(
        cleaned_line.strip() for cleaned_line in check_dirty_working_tree_fn() if cleaned_line.strip()
    )
    if not dirty_tracked_files:
        return

    max_reported_files = 20
    reported_files = dirty_tracked_files[:max_reported_files]
    dirty_files_details = "\n".join(reported_files)
    hidden_file_count = len(dirty_tracked_files) - len(reported_files)
    if hidden_file_count > 0:
        dirty_files_details = f"{dirty_files_details}\n... ({hidden_file_count} more files)"

    raise click.ClickException(
        "Working tree has uncommitted tracked changes. "
        "Commit or stash before shipping, or pass --allow-dirty to override.\n"
        f"{dirty_files_details}"
    )


def execute_ship(
    *,
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
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], DokploySourceOfTruth | None],
    find_dokploy_target_definition_fn: Callable[..., DokployTargetDefinition | None],
    resolve_ship_timeout_seconds_fn: Callable[..., int],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    prepare_ship_branch_sync_fn: Callable[[str, DokployTargetDefinition | None], ShipBranchSyncPlan | None],
    run_required_gates_fn: Callable[..., None],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    read_dokploy_config_fn: Callable[[dict[str, str]], tuple[str, str]],
    resolve_dokploy_compose_name_fn: Callable[[str, str, dict[str, str]], str],
    resolve_dokploy_app_name_fn: Callable[[str, str, dict[str, str]], str],
    resolve_dokploy_target_fn: Callable[..., tuple[str, str, str, click.ClickException | None, click.ClickException | None]],
    apply_ship_branch_sync_fn: Callable[[ShipBranchSyncPlan], None],
    dokploy_request_fn: Callable[..., JsonObject],
    latest_deployment_for_compose_fn: Callable[[str, str, str], JsonObject | None],
    deployment_key_fn: Callable[[JsonObject], str],
    wait_for_dokploy_compose_deployment_fn: Callable[..., str],
    verify_ship_healthchecks_fn: Callable[..., None],
    latest_deployment_for_application_fn: Callable[[str, str, str], JsonObject | None],
    wait_for_dokploy_deployment_fn: Callable[..., str],
    echo_fn: Callable[[str], None],
    allow_dirty: bool = False,
    check_dirty_working_tree_fn: Callable[[], tuple[str, ...]] | None = None,
) -> None:
    _assert_release_context_supported(context_name=context_name, operation_name="Ship")

    runtime_environment = _load_runtime_environment(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_environment_fn=load_environment_fn,
    )
    environment_values = runtime_environment.environment_values
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(runtime_environment.repo_root)
    if source_of_truth is None:
        raise click.ClickException(
            "Ship requires platform/dokploy.toml source of truth. Add the target definition before shipping."
        )
    target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise click.ClickException(
            f"Ship target {context_name}/{instance_name} is missing from platform/dokploy.toml."
        )

    _assert_clean_working_tree(
        allow_dirty=allow_dirty,
        check_dirty_working_tree_fn=check_dirty_working_tree_fn,
    )

    deploy_timeout_seconds = resolve_ship_timeout_seconds_fn(
        timeout_override_seconds=timeout_override_seconds,
        target_definition=target_definition,
    )
    health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )
    healthcheck_urls = resolve_ship_healthcheck_urls_fn(
        target_definition=target_definition,
        environment_values=environment_values,
    )
    should_verify_health = verify_health and wait
    ship_branch_sync_plan = prepare_ship_branch_sync_fn(source_git_ref, target_definition)

    if ship_branch_sync_plan is None:
        echo_fn("branch_sync=false")
    else:
        echo_fn("branch_sync=true")
        echo_fn(f"branch_sync_target_branch={ship_branch_sync_plan.target_branch}")
        echo_fn(f"branch_sync_source_ref={ship_branch_sync_plan.source_git_ref}")
        echo_fn(f"branch_sync_source_commit={ship_branch_sync_plan.source_commit}")
        echo_fn(f"branch_sync_remote_before={ship_branch_sync_plan.remote_branch_commit_before or 'missing'}")
        echo_fn(f"branch_sync_update_required={str(ship_branch_sync_plan.branch_update_required).lower()}")

    run_required_gates_fn(
        context_name=context_name,
        target_definition=target_definition,
        dry_run=dry_run,
        skip_gate=skip_gate,
    )
    ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    try:
        host, token = read_dokploy_config_fn(environment_values)
    except click.ClickException as error:
        if dry_run:
            target_name = resolve_dokploy_compose_name_fn(context_name, instance_name, environment_values)
            if ship_mode == "application":
                target_name = resolve_dokploy_app_name_fn(context_name, instance_name, environment_values)
            echo_fn(f"ship_mode=dokploy-{ship_mode}-api")
            echo_fn(f"target_name={target_name}")
            echo_fn(f"dry_run_note={error.message}")
            echo_fn(f"deploy_timeout_seconds={deploy_timeout_seconds}")
            echo_fn(f"verify_health={str(should_verify_health).lower()}")
            if ship_branch_sync_plan is not None:
                echo_fn("branch_sync_applied=false")
            _echo_healthcheck_plan(
                should_verify_health=should_verify_health,
                health_timeout_seconds=health_timeout_seconds,
                healthcheck_urls=healthcheck_urls,
                echo_fn=echo_fn,
            )
            return
        raise

    (
        selected_target_type,
        selected_target_id,
        selected_target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = resolve_dokploy_target_fn(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
        ship_mode=ship_mode,
        target_definition=target_definition,
    )

    if not selected_target_type:
        messages = ["No Dokploy deployment target resolved."]
        if compose_resolution_error is not None:
            messages.append(f"compose_error={compose_resolution_error.message}")
        if app_resolution_error is not None:
            messages.append(f"application_error={app_resolution_error.message}")
        raise click.ClickException(" ".join(messages))

    if ship_branch_sync_plan is not None:
        if dry_run:
            echo_fn("branch_sync_applied=false")
        else:
            apply_ship_branch_sync_fn(ship_branch_sync_plan)
            echo_fn(f"branch_sync_applied={str(ship_branch_sync_plan.branch_update_required).lower()}")

    if selected_target_type == "compose":
        compose_endpoint = "/api/compose.redeploy" if no_cache else "/api/compose.deploy"
        compose_payload: JsonObject = {"composeId": selected_target_id}
        if no_cache:
            compose_payload["title"] = "Manual redeploy (no-cache requested)"
        deployment_before_key = ""

        _emit_deploy_plan(
            target_mode="dokploy-compose-api",
            target_label_key="compose_name",
            target_label_value=selected_target_name,
            target_id_key="compose_id",
            target_id_value=selected_target_id,
            no_cache=no_cache,
            deploy_timeout_seconds=deploy_timeout_seconds,
            should_verify_health=should_verify_health,
            health_timeout_seconds=health_timeout_seconds,
            healthcheck_urls=healthcheck_urls,
            echo_fn=echo_fn,
        )
        if dry_run:
            return

        if wait:
            latest_before = latest_deployment_for_compose_fn(host, token, selected_target_id)
            deployment_before_key = deployment_key_fn(latest_before or {})

        dokploy_request_fn(
            host=host,
            token=token,
            path=compose_endpoint,
            method="POST",
            payload=compose_payload,
        )
        echo_fn("deploy_triggered=true")
        if not wait:
            return
        result = wait_for_dokploy_compose_deployment_fn(
            host=host,
            token=token,
            compose_id=selected_target_id,
            before_key=deployment_before_key,
            timeout_seconds=deploy_timeout_seconds,
        )
        echo_fn(result)
        if should_verify_health:
            if not healthcheck_urls:
                raise click.ClickException(
                    "Healthcheck verification requested but no target domain/URL was resolved. "
                    "Define domains in platform/dokploy.toml or disable with --no-verify-health."
                )
            verify_ship_healthchecks_fn(urls=healthcheck_urls, timeout_seconds=health_timeout_seconds)
        return

    application_endpoint = "/api/application.redeploy" if no_cache else "/api/application.deploy"
    application_payload: JsonObject = {"applicationId": selected_target_id}
    if no_cache:
        application_payload["title"] = "Manual redeploy (no-cache requested)"
    deployment_before_key = ""

    _emit_deploy_plan(
        target_mode="dokploy-api",
        target_label_key="app_name",
        target_label_value=selected_target_name,
        target_id_key="application_id",
        target_id_value=selected_target_id,
        no_cache=no_cache,
        deploy_timeout_seconds=deploy_timeout_seconds,
        should_verify_health=should_verify_health,
        health_timeout_seconds=health_timeout_seconds,
        healthcheck_urls=healthcheck_urls,
        echo_fn=echo_fn,
    )
    if dry_run:
        return

    if wait:
        latest_before = latest_deployment_for_application_fn(host, token, selected_target_id)
        deployment_before_key = deployment_key_fn(latest_before or {})

    dokploy_request_fn(
        host=host,
        token=token,
        path=application_endpoint,
        method="POST",
        payload=application_payload,
    )
    echo_fn("deploy_triggered=true")
    if not wait:
        return
    result = wait_for_dokploy_deployment_fn(
        host=host,
        token=token,
        application_id=selected_target_id,
        before_key=deployment_before_key,
        timeout_seconds=deploy_timeout_seconds,
    )
    echo_fn(result)
    if should_verify_health:
        if not healthcheck_urls:
            raise click.ClickException(
                "Healthcheck verification requested but no target domain/URL was resolved. "
                "Define domains in platform/dokploy.toml or disable with --no-verify-health."
            )
        verify_ship_healthchecks_fn(urls=healthcheck_urls, timeout_seconds=health_timeout_seconds)


def execute_rollback(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    rollback_id: str,
    list_only: bool,
    wait: bool,
    timeout_seconds: int,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], DokploySourceOfTruth | None],
    find_dokploy_target_definition_fn: Callable[..., DokployTargetDefinition | None],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    read_dokploy_config_fn: Callable[[dict[str, str]], tuple[str, str]],
    resolve_dokploy_app_name_fn: Callable[[str, str, dict[str, str]], str],
    resolve_dokploy_application_id_fn: Callable[..., tuple[str, str]],
    dokploy_request_fn: Callable[..., JsonObject],
    extract_deployments_fn: Callable[[JsonObject], list[JsonObject]],
    collect_rollback_ids_fn: Callable[[list[JsonObject]], list[str]],
    latest_deployment_for_application_fn: Callable[[str, str, str], JsonObject | None],
    deployment_key_fn: Callable[[JsonObject], str],
    wait_for_dokploy_deployment_fn: Callable[..., str],
    echo_fn: Callable[[str], None],
) -> None:
    _assert_release_context_supported(context_name=context_name, operation_name="Rollback")

    runtime_environment = _load_runtime_environment(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_environment_fn=load_environment_fn,
    )
    environment_values = runtime_environment.environment_values
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(runtime_environment.repo_root)
    target_definition = None
    if source_of_truth is not None:
        target_definition = find_dokploy_target_definition_fn(
            source_of_truth,
            context_name=context_name,
            instance_name=instance_name,
        )
    ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    if ship_mode == "compose":
        raise click.ClickException("Rollback in compose ship mode is not supported yet. Use Dokploy UI rollback controls.")
    try:
        host, token = read_dokploy_config_fn(environment_values)
    except click.ClickException as error:
        if dry_run:
            app_name = resolve_dokploy_app_name_fn(context_name, instance_name, environment_values)
            if target_definition is not None and target_definition.target_type == "application":
                app_name = target_definition.target_name.strip() or app_name
            echo_fn(f"app_name={app_name}")
            echo_fn(f"dry_run_note={error.message}")
            return
        raise

    if target_definition is not None and target_definition.target_id.strip():
        if target_definition.target_type != "application":
            raise click.ClickException(
                "Rollback requires an application target, but platform/dokploy.toml "
                f"configures {context_name}/{instance_name} as '{target_definition.target_type}'."
            )
        application_id = target_definition.target_id.strip()
        app_name = target_definition.target_name.strip() or resolve_dokploy_app_name_fn(
            context_name,
            instance_name,
            environment_values,
        )
    else:
        application_id, app_name = resolve_dokploy_application_id_fn(
            host=host,
            token=token,
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )

    deployment_payload = dokploy_request_fn(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = extract_deployments_fn(deployment_payload)
    discovered_rollback_ids = collect_rollback_ids_fn(deployments)

    echo_fn(f"app_name={app_name}")
    echo_fn(f"application_id={application_id}")

    if list_only:
        echo_fn(json.dumps({"rollback_ids": discovered_rollback_ids}, indent=2))
        return

    selected_rollback_id = rollback_id.strip()
    if not selected_rollback_id:
        if not discovered_rollback_ids:
            raise click.ClickException(
                "No rollback ids discovered for this application. Pass --rollback-id explicitly or run --list."
            )
        selected_rollback_id = discovered_rollback_ids[0]

    latest_before = latest_deployment_for_application_fn(host, token, application_id)
    before_key = deployment_key_fn(latest_before or {})

    echo_fn(f"rollback_id={selected_rollback_id}")
    if dry_run:
        return

    dokploy_request_fn(
        host=host,
        token=token,
        path="/api/rollback.rollback",
        method="POST",
        payload={"rollbackId": selected_rollback_id},
    )
    echo_fn("rollback_triggered=true")
    if not wait:
        return
    result = wait_for_dokploy_deployment_fn(
        host=host,
        token=token,
        application_id=application_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )
    echo_fn(result)
