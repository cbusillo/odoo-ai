from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import click

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
type JsonObject = dict[str, JsonValue]


class TargetGatePolicy(Protocol):
    instance: str
    require_test_gate: bool
    require_prod_gate: bool


class TargetDefinition(TargetGatePolicy, Protocol):
    git_branch: str


PROD_DATA_MUTATION_WORKFLOWS = frozenset({"restore", "bootstrap"})
PROMOTION_INSTANCE_PATHS = frozenset({("testing", "prod")})


def run_gate_command(command: list[str], *, dry_run: bool, run_command: Callable[[list[str]], None]) -> None:
    if dry_run:
        click.echo(f"$ {' '.join(command)}")
        return
    run_command(command)


def assert_prod_data_workflow_allowed(*, instance_name: str, workflow: str, allow_prod_data_workflow: bool) -> None:
    if instance_name.strip().lower() != "prod":
        return
    normalized_workflow = workflow.strip().lower()
    if normalized_workflow not in PROD_DATA_MUTATION_WORKFLOWS:
        return
    if allow_prod_data_workflow:
        return
    raise click.ClickException(
        "Prod data-mutation workflow blocked by default. "
        "Re-run with --allow-prod-data-workflow only for explicit break-glass operations."
    )


def collect_environment_gate_results(
    *,
    urls: tuple[str, ...],
    timeout_seconds: int,
    wait_for_ship_healthcheck: Callable[[str, int], str],
) -> list[JsonObject]:
    if not urls:
        raise click.ClickException(
            "No healthcheck URLs resolved for environment gate. "
            "Configure domains in platform/dokploy.toml or ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL."
        )

    results: list[JsonObject] = []
    for healthcheck_url in urls:
        healthcheck_result = wait_for_ship_healthcheck(healthcheck_url, timeout_seconds)
        results.append({"url": healthcheck_url, "result": healthcheck_result})
    return results


def assert_promote_path_allowed(*, from_instance_name: str, to_instance_name: str) -> None:
    normalized_from_instance = from_instance_name.strip().lower()
    normalized_to_instance = to_instance_name.strip().lower()
    if (normalized_from_instance, normalized_to_instance) in PROMOTION_INSTANCE_PATHS:
        return
    raise click.ClickException(
        "Unsupported promotion path. "
        "Only --from-instance testing --to-instance prod is currently allowed."
    )


def validate_target_gate_policy(*, target_definition: TargetGatePolicy) -> None:
    normalized_instance = target_definition.instance.strip().lower()
    if target_definition.require_test_gate and normalized_instance != "testing":
        raise click.ClickException(
            "Invalid gate policy in platform/dokploy.toml: "
            "require_test_gate=true is only allowed for testing targets."
        )
    if target_definition.require_prod_gate and normalized_instance != "prod":
        raise click.ClickException(
            "Invalid gate policy in platform/dokploy.toml: "
            "require_prod_gate=true is only allowed for prod targets."
        )


def run_required_gates(
    *,
    context_name: str,
    target_definition: TargetGatePolicy | None,
    dry_run: bool,
    skip_gate: bool,
    validate_target_gate_policy_fn: Callable[..., None],
    run_code_gate_fn: Callable[..., None],
    run_production_backup_gate_fn: Callable[..., None],
    echo_fn: Callable[[str], None] | None = None,
) -> None:
    if target_definition is None:
        return

    if skip_gate:
        if target_definition.require_test_gate or target_definition.require_prod_gate:
            warning_parts = [
                "warning: skip_gate=true bypassing required gate policy",
            ]
            if target_definition.require_test_gate:
                warning_parts.append("require_test_gate=true")
            if target_definition.require_prod_gate:
                warning_parts.append("require_prod_gate=true")
            warning_message = " ".join(warning_parts)
            if echo_fn is None:
                click.echo(warning_message)
            else:
                echo_fn(warning_message)
        return

    validate_target_gate_policy_fn(target_definition=target_definition)

    if target_definition.require_test_gate:
        run_code_gate_fn(context_name=context_name, dry_run=dry_run)

    if target_definition.require_prod_gate:
        run_production_backup_gate_fn(context_name=context_name, dry_run=dry_run)


def execute_gate(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    phase: str,
    health_timeout_override_seconds: int | None,
    dry_run: bool,
    json_output: bool,
    run_code_gate_fn: Callable[..., None],
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], object | None],
    find_dokploy_target_definition_fn: Callable[..., TargetDefinition | None],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    dokploy_status_payload_fn: Callable[..., JsonObject],
    collect_environment_gate_results_fn: Callable[..., list[JsonObject]],
    emit_payload_fn: Callable[..., None],
) -> None:
    normalized_phase = phase.strip().lower()
    payload: JsonObject = {
        "context": context_name,
        "instance": instance_name,
        "phase": normalized_phase,
        "dry_run": dry_run,
        "code_gate": "skipped",
        "environment_gate": "skipped",
    }

    if normalized_phase in {"code", "all"}:
        run_code_gate_fn(context_name=context_name, dry_run=dry_run)
        payload["code_gate"] = "pass"

    if normalized_phase in {"env", "all"}:
        repo_root = discover_repo_root_fn(Path.cwd())
        _env_file_path, environment_values = load_environment_fn(
            repo_root,
            env_file,
            context_name=context_name,
            instance_name=instance_name,
            collision_mode="error",
        )
        source_of_truth = load_dokploy_source_of_truth_if_present_fn(repo_root)
        target_definition = None
        if source_of_truth is not None:
            target_definition = find_dokploy_target_definition_fn(
                source_of_truth,
                context_name=context_name,
                instance_name=instance_name,
            )

        health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
            health_timeout_override_seconds=health_timeout_override_seconds,
            target_definition=target_definition,
        )
        healthcheck_urls = resolve_ship_healthcheck_urls_fn(
            target_definition=target_definition,
            environment_values=environment_values,
        )

        dokploy_status = dokploy_status_payload_fn(
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )
        payload["dokploy"] = dokploy_status
        if bool(dokploy_status.get("enabled")) and dokploy_status.get("error"):
            raise click.ClickException(f"Environment gate failed: {dokploy_status['error']}")

        if not healthcheck_urls:
            raise click.ClickException(
                "Environment gate failed: no healthcheck URLs resolved. "
                "Configure platform/dokploy.toml domains or ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL."
            )

        payload["health_timeout_seconds"] = health_timeout_seconds
        payload["healthcheck_urls"] = list(healthcheck_urls)
        if dry_run:
            dry_run_results: list[JsonValue] = []
            for healthcheck_url in healthcheck_urls:
                dry_run_results.append({"url": healthcheck_url, "result": "dry-run"})
            payload["healthcheck_results"] = dry_run_results
        else:
            healthcheck_results_payload: list[JsonValue] = []
            for gate_result in collect_environment_gate_results_fn(
                urls=healthcheck_urls,
                timeout_seconds=health_timeout_seconds,
            ):
                healthcheck_results_payload.append(gate_result)
            payload["healthcheck_results"] = healthcheck_results_payload
        payload["environment_gate"] = "pass"

    emit_payload_fn(payload, json_output=json_output)


def execute_promote(
    *,
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
    assert_promote_path_allowed_fn: Callable[..., None],
    discover_repo_root_fn: Callable[[Path], Path],
    load_dokploy_source_of_truth_if_present_fn: Callable[[Path], object | None],
    find_dokploy_target_definition_fn: Callable[..., TargetDefinition | None],
    run_command_fn: Callable[[list[str]], None],
    resolve_remote_git_branch_commit_fn: Callable[[str, str], str],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    resolve_ship_health_timeout_seconds_fn: Callable[..., int],
    resolve_ship_healthcheck_urls_fn: Callable[..., tuple[str, ...]],
    collect_environment_gate_results_fn: Callable[..., list[JsonObject]],
    run_production_backup_gate_fn: Callable[..., None],
    invoke_platform_command_fn: Callable[..., None],
    echo_fn: Callable[[str], None],
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Promote currently supports cm/opw contexts.")
    if from_instance_name == to_instance_name:
        raise click.ClickException("from-instance and to-instance must be different.")
    assert_promote_path_allowed_fn(
        from_instance_name=from_instance_name,
        to_instance_name=to_instance_name,
    )

    repo_root = discover_repo_root_fn(Path.cwd())
    source_of_truth = load_dokploy_source_of_truth_if_present_fn(repo_root)
    if source_of_truth is None:
        raise click.ClickException("Promotion requires platform/dokploy.toml with git branches per target.")

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

    source_branch = source_target_definition.git_branch.strip()
    if not source_branch:
        raise click.ClickException(f"Source target {context_name}/{from_instance_name} is missing git_branch.")

    run_command_fn(["git", "fetch", "origin", "--prune"])
    source_commit = resolve_remote_git_branch_commit_fn("origin", source_branch)
    if not source_commit:
        raise click.ClickException(f"Unable to resolve source commit from origin/{source_branch}.")

    echo_fn(f"promote_context={context_name}")
    echo_fn(f"promote_from_instance={from_instance_name}")
    echo_fn(f"promote_to_instance={to_instance_name}")
    echo_fn(f"promote_source_branch={source_branch}")
    echo_fn(f"promote_source_commit={source_commit}")
    echo_fn(f"promote_destination_branch={destination_target_definition.git_branch}")

    if verify_source_health:
        _env_file_path, source_environment_values = load_environment_fn(
            repo_root,
            env_file,
            context_name=context_name,
            instance_name=from_instance_name,
            collision_mode="error",
        )
        source_health_timeout_seconds = resolve_ship_health_timeout_seconds_fn(
            health_timeout_override_seconds=source_health_timeout_override_seconds,
            target_definition=source_target_definition,
        )
        source_healthcheck_urls = resolve_ship_healthcheck_urls_fn(
            target_definition=source_target_definition,
            environment_values=source_environment_values,
        )
        echo_fn(f"source_health_verify={str(True).lower()}")
        echo_fn(f"source_health_timeout_seconds={source_health_timeout_seconds}")
        for source_healthcheck_url in source_healthcheck_urls:
            echo_fn(f"source_healthcheck_url={source_healthcheck_url}")
        if not dry_run:
            collect_environment_gate_results_fn(urls=source_healthcheck_urls, timeout_seconds=source_health_timeout_seconds)
            echo_fn("source_healthcheck_result=pass")

    echo_fn("prod_backup_gate=true")
    run_production_backup_gate_fn(context_name=context_name, dry_run=dry_run)
    if not dry_run:
        echo_fn("prod_backup_gate_result=pass")

    invoke_platform_command_fn(
        "ship",
        context_name=context_name,
        instance_name=to_instance_name,
        env_file=env_file,
        wait=wait,
        timeout_override_seconds=timeout_override_seconds,
        verify_health=verify_health,
        health_timeout_override_seconds=health_timeout_override_seconds,
        dry_run=dry_run,
        no_cache=no_cache,
        skip_gate=True,
        source_git_ref=source_commit,
    )
