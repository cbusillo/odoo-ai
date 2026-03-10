from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import click

from .models import DokploySourceOfTruth, JsonObject, JsonValue, LoadedStack

RECONCILE_PRUNABLE_ENV_PREFIXES = ("ENV_OVERRIDE_",)
RECONCILE_PRUNABLE_ENV_KEYS = frozenset({"ODOO_WEB_COMMAND"})


@dataclass(frozen=True)
class DokployTargetRuntime:
    target_type: str
    target_id: str
    target_name: str
    host: str
    token: str


def _is_reconcile_prunable_env_key(env_key: str) -> bool:
    if env_key in RECONCILE_PRUNABLE_ENV_KEYS:
        return True
    return env_key.startswith(RECONCILE_PRUNABLE_ENV_PREFIXES)


def _load_target_payload_and_env_map(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    parse_dokploy_env_text_fn: Callable[[str], dict[str, str]],
) -> tuple[DokployTargetRuntime, JsonObject, dict[str, str]]:
    target_runtime = _resolve_target_runtime(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        discover_repo_root_fn=discover_repo_root_fn,
        resolve_dokploy_runtime_fn=resolve_dokploy_runtime_fn,
    )
    target_payload = fetch_dokploy_target_payload_fn(
        host=target_runtime.host,
        token=target_runtime.token,
        target_type=target_runtime.target_type,
        target_id=target_runtime.target_id,
    )
    env_map = parse_dokploy_env_text_fn(str(target_payload.get("env") or ""))
    return target_runtime, target_payload, env_map


def _resolve_target_runtime(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
) -> DokployTargetRuntime:
    repo_root = discover_repo_root_fn(Path.cwd())
    host, token, resolved_target_type, resolved_target_id, resolved_target_name, _environment_values = resolve_dokploy_runtime_fn(
        repo_root=repo_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        target_type=target_type,
    )
    return DokployTargetRuntime(
        target_type=resolved_target_type,
        target_id=resolved_target_id,
        target_name=resolved_target_name,
        host=host,
        token=token,
    )


def execute_env_get(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    keys: tuple[str, ...],
    prefixes: tuple[str, ...],
    show_values: bool,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    parse_dokploy_env_text_fn: Callable[[str], dict[str, str]],
    emit_payload_fn: Callable[..., None],
) -> None:
    target_runtime, _target_payload, env_map = _load_target_payload_and_env_map(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        discover_repo_root_fn=discover_repo_root_fn,
        resolve_dokploy_runtime_fn=resolve_dokploy_runtime_fn,
        fetch_dokploy_target_payload_fn=fetch_dokploy_target_payload_fn,
        parse_dokploy_env_text_fn=parse_dokploy_env_text_fn,
    )

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
        rendered_env[env_key] = env_map[env_key] if show_values else "<redacted>"

    payload = {
        "context": context_name,
        "instance": instance_name,
        "target_type": target_runtime.target_type,
        "target_id": target_runtime.target_id,
        "target_name": target_runtime.target_name,
        "total_env_keys": len(env_map),
        "matched_env_keys": len(selected_keys),
        "show_values": show_values,
        "env": rendered_env,
    }
    emit_payload_fn(payload, json_output=json_output)


def execute_env_set(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    assignments: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
    parse_env_assignment_fn: Callable[[str], tuple[str, str]],
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    parse_dokploy_env_text_fn: Callable[[str], dict[str, str]],
    update_dokploy_target_env_fn: Callable[..., None],
    serialize_dokploy_env_text_fn: Callable[[dict[str, str]], str],
    emit_payload_fn: Callable[..., None],
) -> None:
    parsed_assignments: dict[str, str] = {}
    for assignment in assignments:
        env_key, env_value = parse_env_assignment_fn(assignment)
        parsed_assignments[env_key] = env_value

    target_runtime, target_payload, env_map = _load_target_payload_and_env_map(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        discover_repo_root_fn=discover_repo_root_fn,
        resolve_dokploy_runtime_fn=resolve_dokploy_runtime_fn,
        fetch_dokploy_target_payload_fn=fetch_dokploy_target_payload_fn,
        parse_dokploy_env_text_fn=parse_dokploy_env_text_fn,
    )

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
        update_dokploy_target_env_fn(
            host=target_runtime.host,
            token=target_runtime.token,
            target_type=target_runtime.target_type,
            target_id=target_runtime.target_id,
            target_payload=target_payload,
            env_text=serialize_dokploy_env_text_fn(env_map),
        )

    payload = {
        "context": context_name,
        "instance": instance_name,
        "target_type": target_runtime.target_type,
        "target_id": target_runtime.target_id,
        "target_name": target_runtime.target_name,
        "requested_keys": list(parsed_assignments.keys()),
        "changed_keys": changed_keys,
        "unchanged_keys": unchanged_keys,
        "updated": bool(changed_keys) and not dry_run,
        "dry_run": dry_run,
    }
    emit_payload_fn(payload, json_output=json_output)


def execute_env_unset(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    keys: tuple[str, ...],
    prefixes: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    parse_dokploy_env_text_fn: Callable[[str], dict[str, str]],
    update_dokploy_target_env_fn: Callable[..., None],
    serialize_dokploy_env_text_fn: Callable[[dict[str, str]], str],
    emit_payload_fn: Callable[..., None],
) -> None:
    if not keys and not prefixes:
        raise click.ClickException("Specify at least one --key or --prefix for env-unset.")

    target_runtime, target_payload, env_map = _load_target_payload_and_env_map(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        discover_repo_root_fn=discover_repo_root_fn,
        resolve_dokploy_runtime_fn=resolve_dokploy_runtime_fn,
        fetch_dokploy_target_payload_fn=fetch_dokploy_target_payload_fn,
        parse_dokploy_env_text_fn=parse_dokploy_env_text_fn,
    )

    removed_keys: list[str] = []
    requested_keys = set(keys)
    for env_key in list(env_map.keys()):
        if env_key in requested_keys or any(env_key.startswith(prefix) for prefix in prefixes):
            env_map.pop(env_key, None)
            removed_keys.append(env_key)

    if removed_keys and not dry_run:
        update_dokploy_target_env_fn(
            host=target_runtime.host,
            token=target_runtime.token,
            target_type=target_runtime.target_type,
            target_id=target_runtime.target_id,
            target_payload=target_payload,
            env_text=serialize_dokploy_env_text_fn(env_map),
        )

    payload = {
        "context": context_name,
        "instance": instance_name,
        "target_type": target_runtime.target_type,
        "target_id": target_runtime.target_id,
        "target_name": target_runtime.target_name,
        "removed_keys": removed_keys,
        "updated": bool(removed_keys) and not dry_run,
        "dry_run": dry_run,
    }
    emit_payload_fn(payload, json_output=json_output)


def execute_logs(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    target_type: str,
    limit: int,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    resolve_dokploy_runtime_fn: Callable[..., tuple[str, str, str, str, str, dict[str, str]]],
    dokploy_request_fn: Callable[..., JsonObject],
    extract_deployments_fn: Callable[[JsonObject], list[JsonObject]],
    summarize_deployment_fn: Callable[[JsonObject | None], JsonObject | None],
    emit_payload_fn: Callable[..., None],
) -> None:
    if limit <= 0:
        raise click.ClickException("--limit must be greater than zero.")

    target_runtime = _resolve_target_runtime(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        target_type=target_type,
        discover_repo_root_fn=discover_repo_root_fn,
        resolve_dokploy_runtime_fn=resolve_dokploy_runtime_fn,
    )

    deployment_payload = dokploy_request_fn(
        host=target_runtime.host,
        token=target_runtime.token,
        path="/api/deployment.allByType",
        query={"type": target_runtime.target_type, "id": target_runtime.target_id},
    )
    deployments = extract_deployments_fn(deployment_payload)

    def deployment_sort_key(deployment_payload_item: JsonObject) -> str:
        return str(deployment_payload_item.get("createdAt") or "")

    deployment_items = sorted(deployments, key=deployment_sort_key, reverse=True)[:limit]
    rendered_deployments: list[JsonObject] = []
    for deployment_item in deployment_items:
        deployment_summary = summarize_deployment_fn(deployment_item) or {}
        for key_name, output_key in (
            ("startedAt", "started_at"),
            ("finishedAt", "finished_at"),
            ("serverId", "server_id"),
        ):
            value = deployment_item.get(key_name)
            if value is not None:
                deployment_summary[output_key] = value
        rendered_deployments.append(deployment_summary)

    payload: dict[str, object] = {
        "context": context_name,
        "instance": instance_name,
        "target_type": target_runtime.target_type,
        "target_id": target_runtime.target_id,
        "target_name": target_runtime.target_name,
        "deployments": rendered_deployments,
        "streaming_supported": False,
        "note": "Deployment metadata includes log_path for each run. Direct streaming requires authenticated Dokploy websocket sessions.",
    }
    emit_payload_fn(payload, json_output=json_output)


def _as_object_list(raw_items: object) -> list[JsonObject]:
    object_items: list[JsonObject] = []
    if isinstance(raw_items, dict):
        for key_name in (
            "data",
            "items",
            "result",
            "projects",
            "servers",
            "environments",
            "compose",
            "applications",
        ):
            nested_items = raw_items.get(key_name)
            if isinstance(nested_items, list):
                raw_items = nested_items
                break
    if not isinstance(raw_items, list):
        return object_items
    for raw_item in raw_items:
        if isinstance(raw_item, dict) and all(isinstance(key, str) for key in raw_item):
            object_items.append(raw_item)
    return object_items


def _compose_snapshot_file_name(target_name: str, target_id: str) -> str:
    normalized_target_name = re.sub(r"[^A-Za-z0-9._-]+", "-", target_name.strip()).strip("-") or "compose"
    normalized_target_id = re.sub(r"[^A-Za-z0-9._-]+", "-", target_id.strip()).strip("-") or "unknown"
    return f"{normalized_target_name}--{normalized_target_id}.json"


def execute_inventory(
    *,
    env_file: Path | None,
    output_file: Path | None,
    snapshot_dir: Path | None,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    read_dokploy_config_fn: Callable[[dict[str, str]], tuple[str, str]],
    dokploy_request_fn: Callable[..., JsonValue],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    emit_payload_fn: Callable[..., None],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    _env_file_path, environment_values = load_environment_fn(repo_root, env_file, collision_mode="error")
    host, token = read_dokploy_config_fn(environment_values)

    raw_project_payload = dokploy_request_fn(host=host, token=token, path="/api/project.all")
    raw_server_payload = dokploy_request_fn(host=host, token=token, path="/api/server.all")

    project_items = _as_object_list(raw_project_payload)
    server_items = _as_object_list(raw_server_payload)

    project_summaries: list[dict[str, object]] = []
    compose_target_summaries: list[dict[str, object]] = []
    application_target_summaries: list[dict[str, object]] = []

    for project_item in project_items:
        project_name = str(project_item.get("name") or "")
        project_id = str(project_item.get("projectId") or "")
        environment_summaries: list[dict[str, object]] = []

        for environment_item in _as_object_list(project_item.get("environments")):
            environment_name = str(environment_item.get("name") or "")
            environment_id = str(environment_item.get("environmentId") or "")

            environment_compose_names: list[str] = []
            for compose_item in _as_object_list(environment_item.get("compose")):
                compose_id = str(compose_item.get("composeId") or compose_item.get("compose_id") or "").strip()
                compose_name = str(compose_item.get("name") or "").strip()
                if not compose_id:
                    continue

                target_payload = fetch_dokploy_target_payload_fn(
                    host=host,
                    token=token,
                    target_type="compose",
                    target_id=compose_id,
                )
                raw_domains = target_payload.get("domains")
                domains: list[str] = []
                for domain_item in _as_object_list(raw_domains):
                    domain_host = str(domain_item.get("host") or "").strip()
                    if domain_host:
                        domains.append(domain_host)

                server_object = target_payload.get("server")
                if isinstance(server_object, dict) and all(isinstance(key, str) for key in server_object):
                    server_name = str(server_object.get("name") or "") or None
                    server_ip_address = str(server_object.get("ipAddress") or "") or None
                else:
                    server_name = None
                    server_ip_address = None

                environment_compose_names.append(compose_name or compose_id)
                compose_target_summaries.append(
                    {
                        "project_name": project_name,
                        "project_id": project_id,
                        "environment_name": environment_name,
                        "environment_id": environment_id,
                        "target_type": "compose",
                        "target_id": compose_id,
                        "target_name": compose_name or str(target_payload.get("name") or ""),
                        "app_name": target_payload.get("appName"),
                        "server_id": target_payload.get("serverId"),
                        "server_name": server_name,
                        "server_ip_address": server_ip_address,
                        "domains": sorted(domains),
                        "custom_git_branch": target_payload.get("customGitBranch"),
                        "custom_git_url": target_payload.get("customGitUrl"),
                        "compose_path": target_payload.get("composePath"),
                        "source_type": target_payload.get("sourceType"),
                        "auto_deploy": target_payload.get("autoDeploy"),
                        "compose_status": target_payload.get("composeStatus"),
                    }
                )

            environment_application_names: list[str] = []
            for application_item in _as_object_list(environment_item.get("applications")):
                application_id = str(application_item.get("applicationId") or application_item.get("application_id") or "").strip()
                application_name = str(application_item.get("name") or "").strip()
                if not application_id:
                    continue
                environment_application_names.append(application_name or application_id)
                application_target_summaries.append(
                    {
                        "project_name": project_name,
                        "project_id": project_id,
                        "environment_name": environment_name,
                        "environment_id": environment_id,
                        "target_type": "application",
                        "target_id": application_id,
                        "target_name": application_name,
                    }
                )

            environment_summaries.append(
                {
                    "environment_name": environment_name,
                    "environment_id": environment_id,
                    "compose_targets": sorted(environment_compose_names),
                    "application_targets": sorted(environment_application_names),
                }
            )

        project_summaries.append(
            {
                "project_name": project_name,
                "project_id": project_id,
                "environment_count": len(environment_summaries),
                "environments": environment_summaries,
            }
        )

    server_summaries: list[dict[str, object]] = []
    for server_item in server_items:
        server_summaries.append(
            {
                "server_id": server_item.get("serverId"),
                "server_name": server_item.get("name"),
                "server_type": server_item.get("serverType"),
                "server_status": server_item.get("serverStatus"),
                "ip_address": server_item.get("ipAddress"),
                "username": server_item.get("username"),
                "port": server_item.get("port"),
                "description": server_item.get("description"),
            }
        )

    payload: dict[str, object] = {
        "project_count": len(project_summaries),
        "projects": project_summaries,
        "compose_target_count": len(compose_target_summaries),
        "compose_targets": compose_target_summaries,
        "application_target_count": len(application_target_summaries),
        "application_targets": application_target_summaries,
        "server_count": len(server_summaries),
        "servers": server_summaries,
    }

    if snapshot_dir is not None:
        resolved_snapshot_dir = snapshot_dir if snapshot_dir.is_absolute() else (repo_root / snapshot_dir)
        resolved_snapshot_dir.mkdir(parents=True, exist_ok=True)
        compose_snapshot_dir = resolved_snapshot_dir / "compose"
        compose_snapshot_dir.mkdir(parents=True, exist_ok=True)
        (resolved_snapshot_dir / "project.all.json").write_text(
            json.dumps(raw_project_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        (resolved_snapshot_dir / "server.all.json").write_text(
            json.dumps(raw_server_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        for compose_target in compose_target_summaries:
            compose_target_id = str(compose_target.get("target_id") or "")
            compose_target_name = str(compose_target.get("target_name") or compose_target_id or "compose")
            target_payload = fetch_dokploy_target_payload_fn(
                host=host,
                token=token,
                target_type="compose",
                target_id=compose_target_id,
            )
            snapshot_file_name = _compose_snapshot_file_name(compose_target_name, compose_target_id)
            (compose_snapshot_dir / snapshot_file_name).write_text(
                json.dumps(target_payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        payload["snapshot_dir"] = str(resolved_snapshot_dir)

    _write_payload_file(repo_root=repo_root, output_file=output_file, payload=payload)

    emit_payload_fn(payload, json_output=json_output)


def _read_json_object(file_path: Path, *, label: str) -> JsonObject:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Invalid {label} file {file_path}: {exc}") from exc
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise click.ClickException(f"Invalid {label} file {file_path}: expected a JSON object payload.")
    return payload


def _write_payload_file(*, repo_root: Path, output_file: Path | None, payload: dict[str, object]) -> None:
    if output_file is None:
        return
    resolved_output_file = output_file if output_file.is_absolute() else (repo_root / output_file)
    resolved_output_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["output_file"] = str(resolved_output_file)


def execute_reconcile(
    *,
    stack_file: Path,
    source_file: Path,
    env_file: Path | None,
    context_filter: str | None,
    instance_filter: str | None,
    apply: bool,
    prune_env: bool,
    json_output: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_dokploy_source_file_fn: Callable[[Path, Path | None], Path],
    load_dokploy_source_of_truth_fn: Callable[[Path], DokploySourceOfTruth],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    read_dokploy_config_fn: Callable[[dict[str, str]], tuple[str, str]],
    target_matches_filters_fn: Callable[..., bool],
    fetch_dokploy_target_payload_fn: Callable[..., JsonObject],
    normalize_domains_fn: Callable[[object], list[str]],
    dokploy_request_fn: Callable[..., JsonObject],
    update_dokploy_target_env_fn: Callable[..., None],
    parse_dokploy_env_text_fn: Callable[[str], dict[str, str]],
    serialize_dokploy_env_text_fn: Callable[[dict[str, str]], str],
    emit_payload_fn: Callable[..., None],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = load_stack_fn(stack_file_path)
    source_file_path = resolve_dokploy_source_file_fn(repo_root, source_file)
    source_of_truth = load_dokploy_source_of_truth_fn(source_file_path)

    results: list[dict[str, object]] = []
    matched_targets = [
        target
        for target in source_of_truth.targets
        if target_matches_filters_fn(target, context_filter=context_filter, instance_filter=instance_filter)
    ]
    if not matched_targets:
        raise click.ClickException("No source-of-truth targets matched the requested filters.")

    stack_contexts = loaded_stack.stack_definition.contexts
    for source_target in matched_targets:
        context_name = source_target.context
        instance_name = source_target.instance
        if context_name not in stack_contexts:
            raise click.ClickException(
                f"Target {context_name}/{instance_name} from {source_file_path} is not defined in {stack_file_path}."
            )
        context_definition = stack_contexts[context_name]
        if instance_name not in context_definition.instances:
            raise click.ClickException(
                f"Target {context_name}/{instance_name} from {source_file_path} is not defined in {stack_file_path}."
            )

    for target in matched_targets:
        context_name = target.context
        instance_name = target.instance
        target_type = target.target_type

        _env_file_path, environment_values = load_environment_fn(
            repo_root,
            env_file,
            context_name=context_name,
            instance_name=instance_name,
            collision_mode="error",
        )
        host, token = read_dokploy_config_fn(environment_values)

        resolved_target_id = target.target_id.strip()
        resolved_target_name = target.target_name.strip() or f"{context_name}-{instance_name}"
        if not resolved_target_id:
            raise click.ClickException(
                f"Target {context_name}/{instance_name} in {source_file_path} must define target_id."
            )

        target_payload = fetch_dokploy_target_payload_fn(
            host=host,
            token=token,
            target_type=target_type,
            target_id=resolved_target_id,
        )

        current_target_name = str(target_payload.get("name") or resolved_target_name)
        current_domains = normalize_domains_fn(target_payload.get("domains"))
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
        env_map = parse_dokploy_env_text_fn(str(target_payload.get("env") or ""))
        desired_env = {key: value for key, value in target.env.items() if key}
        env_needs_update_keys: list[str] = []
        env_pruned_keys: list[str] = []
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
                dokploy_request_fn(
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

        if prune_env:
            for env_key in list(env_map.keys()):
                if env_key in desired_env:
                    continue
                if not _is_reconcile_prunable_env_key(env_key):
                    continue
                env_map.pop(env_key, None)
                env_pruned_keys.append(env_key)

        if (env_needs_update_keys or env_pruned_keys) and apply:
            update_dokploy_target_env_fn(
                host=host,
                token=token,
                target_type=target_type,
                target_id=resolved_target_id,
                target_payload=target_payload,
                env_text=serialize_dokploy_env_text_fn(env_map),
            )
            env_updated = True

        results.append(
            {
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
                "desired_env_keys": sorted(desired_env.keys()),
                "env_needs_update_keys": env_needs_update_keys,
                "prune_env": prune_env,
                "env_pruned_keys": env_pruned_keys,
                "env_updated": env_updated,
                "desired_domains": desired_domains,
                "current_domains": current_domains,
                "missing_domains": missing_domains,
                "unexpected_domains": unexpected_domains,
            }
        )

    payload: dict[str, object] = {
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
        "targets": results,
    }
    emit_payload_fn(payload, json_output=json_output)
