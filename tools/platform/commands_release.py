import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import click

from .models import DokploySourceOfTruth, DokployTargetDefinition, JsonObject, ShipRequest
from .process_env import git_command_execution_env

SUPPORTED_RELEASE_CONTEXTS = frozenset({"cm", "opw"})


@dataclass(frozen=True)
class RuntimeEnvironment:
    repo_root: Path
    environment_values: dict[str, str]


@dataclass(frozen=True)
class ShipBranchSyncPlan:
    source_git_ref: str
    source_commit: str
    target_remote_name: str
    target_branch: str
    remote_branch_commit_before: str
    branch_update_required: bool


DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF = "origin/main"


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


def _run_command_capture(command: list[str], *, repo_root: Path) -> str:
    result = subprocess.run(command, capture_output=True, text=True, cwd=repo_root, env=git_command_execution_env())
    if result.returncode != 0:
        joined_command = " ".join(command)
        stderr_text = result.stderr.strip()
        message = f"Command failed ({result.returncode}): {joined_command}"
        if stderr_text:
            message = f"{message}\n{stderr_text}"
        raise click.ClickException(message)
    return result.stdout


def _resolve_local_git_commit(*, repo_root: Path, git_reference: str) -> str:
    raw_output = _run_command_capture(["git", "rev-parse", "--verify", f"{git_reference}^{{commit}}"], repo_root=repo_root)
    return raw_output.strip()


def _git_reference_exists_locally(*, repo_root: Path, git_reference: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{git_reference}^{{commit}}"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=git_command_execution_env(),
    )
    return result.returncode == 0


def _resolve_remote_git_branch_commit(*, repo_root: Path, remote_name: str, branch_name: str) -> str:
    raw_output = _run_command_capture(
        ["git", "ls-remote", "--heads", remote_name, f"refs/heads/{branch_name}"],
        repo_root=repo_root,
    )
    for raw_line in raw_output.splitlines():
        cleaned_line = raw_line.strip()
        if not cleaned_line:
            continue
        split_line = cleaned_line.split()
        if split_line:
            return split_line[0].strip()
    return ""


def _list_git_remotes(*, repo_root: Path) -> tuple[str, ...]:
    raw_output = _run_command_capture(["git", "remote"], repo_root=repo_root)
    remote_names: list[str] = []
    for raw_line in raw_output.splitlines():
        cleaned_line = raw_line.strip()
        if cleaned_line:
            remote_names.append(cleaned_line)
    return tuple(remote_names)


def _resolve_symbolic_full_git_reference(*, repo_root: Path, git_reference: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--symbolic-full-name", "--verify", git_reference],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=git_command_execution_env(),
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_git_remote_for_reference(
    *,
    repo_root: Path,
    git_reference: str,
    configured_remotes: tuple[str, ...] | None = None,
) -> str:
    cleaned_reference = git_reference.strip()
    if not cleaned_reference:
        return ""

    if cleaned_reference.startswith("refs/remotes/"):
        remote_name = cleaned_reference.removeprefix("refs/remotes/").split("/", 1)[0].strip()
        return remote_name

    if cleaned_reference.startswith("refs/"):
        return ""

    symbolic_full_reference = _resolve_symbolic_full_git_reference(repo_root=repo_root, git_reference=cleaned_reference)
    if not symbolic_full_reference.startswith("refs/remotes/"):
        return ""

    candidate_remote_name = symbolic_full_reference.removeprefix("refs/remotes/").split("/", 1)[0].strip()
    resolved_remotes = configured_remotes if configured_remotes is not None else _list_git_remotes(repo_root=repo_root)
    if candidate_remote_name in resolved_remotes:
        return candidate_remote_name
    return ""


def _git_reference_is_remote_tracking(*, repo_root: Path, git_reference: str) -> bool:
    cleaned_reference = git_reference.strip()
    if not cleaned_reference:
        return False
    if cleaned_reference.startswith("refs/remotes/"):
        return True
    if cleaned_reference.startswith("refs/"):
        return False
    symbolic_full_reference = _resolve_symbolic_full_git_reference(repo_root=repo_root, git_reference=cleaned_reference)
    return symbolic_full_reference.startswith("refs/remotes/")


def _infer_git_remote_from_reference_syntax(
    *,
    git_reference: str,
    configured_remotes: tuple[str, ...],
) -> str:
    cleaned_reference = git_reference.strip()
    if not cleaned_reference or cleaned_reference.startswith("refs/") or "/" not in cleaned_reference:
        return ""

    candidate_remote_name = cleaned_reference.split("/", 1)[0].strip()
    if candidate_remote_name in configured_remotes:
        return candidate_remote_name
    return ""


def _resolve_ship_source_git_ref(
    *,
    source_git_ref_override: str,
    target_definition: DokployTargetDefinition | None,
    configured_remotes: tuple[str, ...],
) -> str:
    cleaned_override = source_git_ref_override.strip()
    if cleaned_override:
        return cleaned_override
    if target_definition is not None:
        cleaned_target_reference = target_definition.source_git_ref.strip()
        if cleaned_target_reference:
            return cleaned_target_reference
    if "origin" in configured_remotes:
        return DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF
    if len(configured_remotes) == 1:
        return f"{configured_remotes[0]}/main"
    return "main"


def _resolve_ship_target_remote_name(
    *,
    configured_remotes: tuple[str, ...],
    source_remote_name: str,
) -> str:
    if not configured_remotes:
        raise click.ClickException("Compose ship target requires at least one configured git remote for branch sync.")

    if "origin" in configured_remotes:
        return "origin"

    if source_remote_name and source_remote_name in configured_remotes:
        return source_remote_name

    if len(configured_remotes) == 1:
        return configured_remotes[0]

    remote_names = ", ".join(configured_remotes)
    raise click.ClickException(
        f"Compose ship target could not determine a target remote for branch sync. Configured remotes: {remote_names}."
    )


def _prepare_ship_branch_sync(
    *,
    repo_root: Path,
    source_git_ref_override: str,
    target_definition: DokployTargetDefinition | None,
) -> ShipBranchSyncPlan | None:
    if target_definition is None:
        return None

    target_branch = target_definition.git_branch.strip()
    if not target_branch:
        target_label = target_definition.target_name.strip() or f"{target_definition.context}/{target_definition.instance}"
        raise click.ClickException(
            "Compose ship target requires git_branch for branch sync before deploy: "
            f"target={target_label} context={target_definition.context} instance={target_definition.instance}."
        )

    configured_remotes = _list_git_remotes(repo_root=repo_root)
    source_git_ref = _resolve_ship_source_git_ref(
        source_git_ref_override=source_git_ref_override,
        target_definition=target_definition,
        configured_remotes=configured_remotes,
    )
    source_ref_exists_locally = _git_reference_exists_locally(repo_root=repo_root, git_reference=source_git_ref)
    source_ref_is_remote_tracking = _git_reference_is_remote_tracking(repo_root=repo_root, git_reference=source_git_ref)
    source_remote_name = _resolve_git_remote_for_reference(
        repo_root=repo_root,
        git_reference=source_git_ref,
        configured_remotes=configured_remotes,
    )
    if not source_remote_name and not source_ref_exists_locally:
        source_remote_name = _infer_git_remote_from_reference_syntax(
            git_reference=source_git_ref,
            configured_remotes=configured_remotes,
        )
    target_remote_name = _resolve_ship_target_remote_name(
        configured_remotes=configured_remotes,
        source_remote_name=source_remote_name,
    )
    if source_remote_name and (not source_ref_exists_locally or source_ref_is_remote_tracking):
        _run_command_capture(["git", "fetch", source_remote_name, "--prune"], repo_root=repo_root)
    source_commit = _resolve_local_git_commit(repo_root=repo_root, git_reference=source_git_ref)
    remote_branch_commit_before = _resolve_remote_git_branch_commit(
        repo_root=repo_root,
        remote_name=target_remote_name,
        branch_name=target_branch,
    )
    branch_update_required = source_commit != remote_branch_commit_before
    return ShipBranchSyncPlan(
        source_git_ref=source_git_ref,
        source_commit=source_commit,
        target_remote_name=target_remote_name,
        target_branch=target_branch,
        remote_branch_commit_before=remote_branch_commit_before,
        branch_update_required=branch_update_required,
    )


def _apply_ship_branch_sync(*, repo_root: Path, ship_branch_sync_plan: ShipBranchSyncPlan) -> None:
    if not ship_branch_sync_plan.branch_update_required:
        return

    lease_reference = f"refs/heads/{ship_branch_sync_plan.target_branch}:{ship_branch_sync_plan.remote_branch_commit_before}"
    _run_command_capture(
        [
            "git",
            "push",
            ship_branch_sync_plan.target_remote_name,
            f"--force-with-lease={lease_reference}",
            f"{ship_branch_sync_plan.source_commit}:refs/heads/{ship_branch_sync_plan.target_branch}",
        ],
        repo_root=repo_root,
    )


def _execute_prepared_ship_branch_sync(
    *,
    repo_root: Path,
    ship_branch_sync_plan: ShipBranchSyncPlan,
    echo_fn: Callable[[str], None],
) -> None:
    echo_fn("branch_sync=true")
    echo_fn(f"branch_sync_target_remote={ship_branch_sync_plan.target_remote_name}")
    echo_fn(f"branch_sync_target_branch={ship_branch_sync_plan.target_branch}")
    echo_fn(f"branch_sync_source_ref={ship_branch_sync_plan.source_git_ref}")
    echo_fn(f"branch_sync_source_commit={ship_branch_sync_plan.source_commit}")
    echo_fn(f"branch_sync_remote_before={ship_branch_sync_plan.remote_branch_commit_before or 'missing'}")
    echo_fn(f"branch_sync_update_required={str(ship_branch_sync_plan.branch_update_required).lower()}")
    _apply_ship_branch_sync(repo_root=repo_root, ship_branch_sync_plan=ship_branch_sync_plan)
    echo_fn(f"branch_sync_applied={str(ship_branch_sync_plan.branch_update_required).lower()}")


def _run_ship_branch_sync(
    *,
    repo_root: Path,
    source_git_ref_override: str,
    target_definition: DokployTargetDefinition | None,
    echo_fn: Callable[[str], None],
) -> None:
    ship_branch_sync_plan = _prepare_ship_branch_sync(
        repo_root=repo_root,
        source_git_ref_override=source_git_ref_override,
        target_definition=target_definition,
    )
    if ship_branch_sync_plan is None:
        echo_fn("branch_sync=false")
        return
    _execute_prepared_ship_branch_sync(
        repo_root=repo_root,
        ship_branch_sync_plan=ship_branch_sync_plan,
        echo_fn=echo_fn,
    )


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


def _resolve_deploy_mode(*, configured_ship_mode: str, target_type: str) -> str:
    if configured_ship_mode != "auto" and configured_ship_mode != target_type:
        raise click.ClickException(
            "Configured Dokploy ship mode conflicts with the target definition: "
            f"ship_mode={configured_ship_mode} target_type={target_type}."
        )
    selected_mode = configured_ship_mode if configured_ship_mode != "auto" else target_type
    return f"dokploy-{selected_mode}-api"


def _run_post_deploy_steps(
    *,
    should_verify_health: bool,
    health_timeout_seconds: int,
    healthcheck_urls: tuple[str, ...],
    run_post_deploy_update_fn: Callable[[], None] | None,
    verify_ship_healthchecks_fn: Callable[..., None],
) -> None:
    if should_verify_health and not healthcheck_urls:
        raise click.ClickException(
            "Healthcheck verification requested but no target domain/URL was resolved. "
            "Define domains in platform/dokploy.toml or disable with --no-verify-health."
        )

    if run_post_deploy_update_fn is not None:
        run_post_deploy_update_fn()

    if not should_verify_health:
        return

    verify_ship_healthchecks_fn(urls=healthcheck_urls, timeout_seconds=health_timeout_seconds)


def _resolve_post_deploy_update_fn(
    *,
    selected_target_type: str,
    run_post_deploy_update_fn: Callable[[], None] | None,
    echo_fn: Callable[[str], None],
) -> Callable[[], None] | None:
    if run_post_deploy_update_fn is None:
        return None
    if selected_target_type == "compose":
        return run_post_deploy_update_fn

    echo_fn(f"post_deploy_update=skipped target_type={selected_target_type}")
    return None


def _assert_clean_working_tree(
    *,
    allow_dirty: bool,
    check_dirty_working_tree_fn: Callable[[], tuple[str, ...]] | None,
) -> None:
    if allow_dirty or check_dirty_working_tree_fn is None:
        return
    dirty_tracked_files = tuple(cleaned_line.strip() for cleaned_line in check_dirty_working_tree_fn() if cleaned_line.strip())
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
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], DokploySourceOfTruth | None],
    find_dokploy_target_definition_fn: Callable[..., DokployTargetDefinition | None],
    resolve_ship_timeout_seconds_fn: Callable[..., int],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    run_required_gates_fn: Callable[..., None],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    read_dokploy_config_fn: Callable[[dict[str, str]], tuple[str, str]],
    resolve_dokploy_target_fn: Callable[..., tuple[str, str, str, click.ClickException | None, click.ClickException | None]],
    dokploy_request_fn: Callable[..., JsonObject],
    latest_deployment_for_compose_fn: Callable[[str, str, str], JsonObject | None],
    deployment_key_fn: Callable[[JsonObject], str],
    wait_for_dokploy_compose_deployment_fn: Callable[..., str],
    verify_ship_healthchecks_fn: Callable[..., None],
    latest_deployment_for_application_fn: Callable[[str, str, str], JsonObject | None],
    wait_for_dokploy_deployment_fn: Callable[..., str],
    echo_fn: Callable[[str], None],
    run_post_deploy_update_fn: Callable[[], None] | None = None,
    allow_dirty: bool = False,
    check_dirty_working_tree_fn: Callable[[], tuple[str, ...]] | None = None,
    source_git_ref: str = "",
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
        raise click.ClickException("Ship requires platform/dokploy.toml source of truth. Add the target definition before shipping.")
    target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise click.ClickException(f"Ship target {context_name}/{instance_name} is missing from platform/dokploy.toml.")

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

    ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    try:
        host, token = read_dokploy_config_fn(environment_values)
    except click.ClickException as error:
        if dry_run:
            target_name = target_definition.target_name.strip() or f"{context_name}-{instance_name}"
            echo_fn(f"ship_mode=dokploy-{ship_mode}-api")
            echo_fn(f"target_name={target_name}")
            echo_fn(f"dry_run_note={error.message}")
            echo_fn(f"deploy_timeout_seconds={deploy_timeout_seconds}")
            echo_fn(f"verify_health={str(should_verify_health).lower()}")
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

    post_deploy_update_fn = _resolve_post_deploy_update_fn(
        selected_target_type=selected_target_type,
        run_post_deploy_update_fn=run_post_deploy_update_fn,
        echo_fn=echo_fn,
    )

    should_run_branch_sync = selected_target_type == "compose" or bool(target_definition.git_branch.strip())
    prepared_ship_branch_sync_plan: ShipBranchSyncPlan | None = None
    repo_has_git_metadata = (runtime_environment.repo_root / ".git").exists()
    explicit_source_ref_requested = bool(source_git_ref.strip()) or (
        bool(target_definition.source_git_ref.strip())
        and target_definition.source_git_ref.strip() != DEFAULT_DOKPLOY_SHIP_SOURCE_GIT_REF
    )
    if should_run_branch_sync and not dry_run and explicit_source_ref_requested and not repo_has_git_metadata:
        raise click.ClickException(
            "Ship requires git metadata in the runtime checkout when an explicit source ref must be pinned before gates."
        )
    if should_run_branch_sync and not dry_run and repo_has_git_metadata:
        prepared_ship_branch_sync_plan = _prepare_ship_branch_sync(
            repo_root=runtime_environment.repo_root,
            source_git_ref_override=source_git_ref,
            target_definition=target_definition,
        )

    run_required_gates_fn(
        context_name=context_name,
        target_definition=target_definition,
        dry_run=dry_run,
        skip_gate=skip_gate,
    )
    branch_sync_completed = False

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

        if should_run_branch_sync and not branch_sync_completed:
            if prepared_ship_branch_sync_plan is not None:
                _execute_prepared_ship_branch_sync(
                    repo_root=runtime_environment.repo_root,
                    ship_branch_sync_plan=prepared_ship_branch_sync_plan,
                    echo_fn=echo_fn,
                )
            else:
                _run_ship_branch_sync(
                    repo_root=runtime_environment.repo_root,
                    source_git_ref_override=source_git_ref,
                    target_definition=target_definition,
                    echo_fn=echo_fn,
                )
            branch_sync_completed = True

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
        _run_post_deploy_steps(
            should_verify_health=should_verify_health,
            health_timeout_seconds=health_timeout_seconds,
            healthcheck_urls=healthcheck_urls,
            run_post_deploy_update_fn=post_deploy_update_fn,
            verify_ship_healthchecks_fn=verify_ship_healthchecks_fn,
        )
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

    if should_run_branch_sync and not branch_sync_completed:
        if prepared_ship_branch_sync_plan is not None:
            _execute_prepared_ship_branch_sync(
                repo_root=runtime_environment.repo_root,
                ship_branch_sync_plan=prepared_ship_branch_sync_plan,
                echo_fn=echo_fn,
            )
        else:
            _run_ship_branch_sync(
                repo_root=runtime_environment.repo_root,
                source_git_ref_override=source_git_ref,
                target_definition=target_definition,
                echo_fn=echo_fn,
            )
        branch_sync_completed = True

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
    _run_post_deploy_steps(
        should_verify_health=should_verify_health,
        health_timeout_seconds=health_timeout_seconds,
        healthcheck_urls=healthcheck_urls,
        run_post_deploy_update_fn=post_deploy_update_fn,
        verify_ship_healthchecks_fn=verify_ship_healthchecks_fn,
    )


def execute_export_ship_request(
    *,
    context_name: str,
    instance_name: str,
    artifact_id: str,
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
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], DokploySourceOfTruth | None],
    find_dokploy_target_definition_fn: Callable[..., DokployTargetDefinition | None],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    resolve_dokploy_ship_mode_fn: Callable[[str, str, dict[str, str]], str],
    emit_payload_fn: Callable[[JsonObject], None],
) -> None:
    _assert_release_context_supported(context_name=context_name, operation_name="Ship request export")
    normalized_artifact_id = artifact_id.strip()
    if not normalized_artifact_id:
        raise click.ClickException("ship request requires artifact_id")

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
        raise click.ClickException("Ship request export requires platform/dokploy.toml source of truth.")
    target_definition = find_dokploy_target_definition_fn(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise click.ClickException(f"Ship target {context_name}/{instance_name} is missing from platform/dokploy.toml.")

    resolved_source_git_ref = source_git_ref.strip() or target_definition.source_git_ref.strip() or default_source_git_ref
    destination_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
        health_timeout_override_seconds=health_timeout_override_seconds,
        target_definition=target_definition,
    )
    destination_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
        target_definition=target_definition,
        environment_values=environment_values,
    )
    should_verify_health = verify_health and wait
    if should_verify_health and not destination_healthcheck_urls:
        raise click.ClickException(
            "Healthcheck verification requested but no target domain/URL was resolved. "
            "Define domains in platform/dokploy.toml or disable with --no-verify-health."
        )
    configured_ship_mode = resolve_dokploy_ship_mode_fn(context_name, instance_name, environment_values)
    deploy_mode = _resolve_deploy_mode(
        configured_ship_mode=configured_ship_mode,
        target_type=target_definition.target_type,
    )

    try:
        ship_request = ShipRequest(
            artifact_id=normalized_artifact_id,
            context=context_name,
            instance=instance_name,
            source_git_ref=resolved_source_git_ref,
            target_name=target_definition.target_name.strip() or f"{context_name}-{instance_name}",
            target_type=target_definition.target_type,
            deploy_mode=deploy_mode,
            wait=wait,
            timeout_seconds=timeout_override_seconds,
            verify_health=should_verify_health,
            health_timeout_seconds=destination_health_timeout_seconds,
            dry_run=dry_run,
            no_cache=no_cache,
            allow_dirty=allow_dirty,
            destination_health={
                "urls": destination_healthcheck_urls,
                "timeout_seconds": destination_health_timeout_seconds,
                "status": "pending" if should_verify_health else "skipped",
            },
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    emit_payload_fn(ship_request.model_dump(mode="json"))


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
            app_name = f"{context_name}-{instance_name}"
            if target_definition is not None and target_definition.target_type == "application":
                app_name = target_definition.target_name.strip() or app_name
            echo_fn(f"app_name={app_name}")
            echo_fn(f"dry_run_note={error.message}")
            return
        raise

    if target_definition is None:
        raise click.ClickException(f"Rollback target {context_name}/{instance_name} is missing from platform/dokploy.toml.")
    if target_definition.target_type != "application":
        raise click.ClickException(
            "Rollback requires an application target, but platform/dokploy.toml "
            f"configures {context_name}/{instance_name} as '{target_definition.target_type}'."
        )

    application_id = target_definition.target_id.strip()
    if not application_id:
        raise click.ClickException(f"Rollback target {context_name}/{instance_name} must define target_id in platform/dokploy.toml.")
    app_name = target_definition.target_name.strip() or f"{context_name}-{instance_name}"

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
