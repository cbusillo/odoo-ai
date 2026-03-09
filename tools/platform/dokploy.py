from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import click
import requests

from tools.platform.models import DokploySourceOfTruth, DokployTargetDefinition, JsonObject, JsonValue

DEFAULT_DOKPLOY_DEPLOY_TIMEOUT_SECONDS = 600
DEFAULT_DOKPLOY_HEALTH_TIMEOUT_SECONDS = 180
DEFAULT_DOKPLOY_HEALTHCHECK_PATH = "/web/health"
HEALTHCHECK_PASS_STATUSES = {"pass", "ok", "healthy"}


def dokploy_request(
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
    try:
        response = requests.request(method, url, headers=headers, json=payload, params=query, timeout=60)
    except requests.RequestException as error:
        raise click.ClickException(f"Dokploy API {method} {normalized_path} request failed: {error}") from error
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


def read_dokploy_config(environment_values: dict[str, str]) -> tuple[str, str]:
    host = environment_values.get("DOKPLOY_HOST", "").strip()
    token = environment_values.get("DOKPLOY_TOKEN", "").strip()
    if not host or not token:
        raise click.ClickException(
            "Missing DOKPLOY_HOST or DOKPLOY_TOKEN in resolved environment "
            "(selected env file and/or platform/secrets.toml)."
        )
    return host, token


def as_json_object(value: JsonValue) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return value


def extract_deployments(raw_payload: JsonValue) -> list[JsonObject]:
    if isinstance(raw_payload, list):
        deployment_items: list[JsonObject] = []
        for item in raw_payload:
            item_as_object = as_json_object(item)
            if item_as_object is not None:
                deployment_items.append(item_as_object)
        return deployment_items
    if isinstance(raw_payload, dict):
        for key in ("data", "deployments", "items", "result"):
            value = raw_payload.get(key)
            if isinstance(value, list):
                deployment_items = []
                for item in value:
                    item_as_object = as_json_object(item)
                    if item_as_object is not None:
                        deployment_items.append(item_as_object)
                return deployment_items
    return []


def deployment_key(deployment: JsonObject) -> str:
    for key in ("deploymentId", "deployment_id", "id", "uuid"):
        value = deployment.get(key)
        if value:
            return str(value)
    return ""


def deployment_status(deployment: JsonObject) -> str:
    for key in ("status", "state", "deploymentStatus"):
        value = deployment.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def _deployment_sort_key(deployment: JsonObject) -> str:
    for key in ("createdAt", "created_at", "updatedAt", "updated_at"):
        value = deployment.get(key)
        if value:
            return str(value)
    return deployment_key(deployment)


def _latest_deployment_from_list(deployments: list[JsonObject]) -> JsonObject | None:
    if not deployments:
        return None
    return max(deployments, key=_deployment_sort_key)


def summarize_deployment(deployment: JsonObject | None) -> JsonObject | None:
    if deployment is None:
        return None
    summary: JsonObject = {
        "deployment_id": deployment_key(deployment),
        "status": deployment_status(deployment),
    }
    for source_key, target_key in (
        ("createdAt", "created_at"),
        ("title", "title"),
        ("description", "description"),
        ("logPath", "log_path"),
    ):
        value = deployment.get(source_key)
        if value is not None:
            summary[target_key] = value
    return summary


def collect_application_records(payload: JsonValue) -> list[JsonObject]:
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


def resolve_dokploy_app_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_APP_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def resolve_dokploy_compose_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_COMPOSE_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def collect_compose_records(payload: JsonValue) -> list[JsonObject]:
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


def resolve_dokploy_compose_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_COMPOSE_ID_{context_name}_{instance_name}".upper()
    explicit_compose_id = environment_values.get(specific_id_key, "").strip()
    compose_name = resolve_dokploy_compose_name(context_name, instance_name, environment_values)
    if explicit_compose_id:
        return explicit_compose_id, compose_name

    projects_payload = dokploy_request(host=host, token=token, path="/api/project.all")
    records = collect_compose_records(projects_payload)
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


def resolve_dokploy_ship_mode(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_SHIP_MODE_{context_name}_{instance_name}".upper()
    configured_mode = environment_values.get(specific_key, "").strip().lower()
    if not configured_mode:
        configured_mode = environment_values.get("DOKPLOY_SHIP_MODE", "auto").strip().lower() or "auto"
    if configured_mode not in {"auto", "compose", "application"}:
        raise click.ClickException(
            f"Invalid Dokploy ship mode '{configured_mode}'. Expected auto, compose, or application."
        )
    return configured_mode


def resolve_dokploy_application_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_APPLICATION_ID_{context_name}_{instance_name}".upper()
    explicit_application_id = environment_values.get(specific_id_key, "").strip()
    app_name = resolve_dokploy_app_name(context_name, instance_name, environment_values)
    if explicit_application_id:
        return explicit_application_id, app_name

    projects_payload = dokploy_request(host=host, token=token, path="/api/project.all")
    records = collect_application_records(projects_payload)
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


def latest_deployment_for_application(host: str, token: str, application_id: str) -> JsonObject | None:
    payload = dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = extract_deployments(payload)
    return _latest_deployment_from_list(deployments)


def latest_deployment_for_compose(host: str, token: str, compose_id: str) -> JsonObject | None:
    compose_payload = dokploy_request(
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
    for deployment_entry in deployments_payload:
        deployment_as_object = as_json_object(cast(JsonValue, deployment_entry))
        if deployment_as_object is not None:
            deployments.append(deployment_as_object)
    return _latest_deployment_from_list(deployments)


def _wait_for_deployment_status(
    *,
    fetch_latest_deployment: Callable[[], JsonObject | None],
    before_key: str,
    timeout_seconds: int,
    failure_message_prefix: str,
) -> str:
    success_statuses = {"success", "succeeded", "done", "completed", "healthy", "finished"}
    failure_statuses = {"failed", "error", "canceled", "cancelled", "killed", "unhealthy", "timeout"}

    start_time = time.monotonic()
    while time.monotonic() - start_time <= timeout_seconds:
        latest = fetch_latest_deployment()
        if not latest:
            time.sleep(3)
            continue

        latest_key = deployment_key(latest)
        latest_status = deployment_status(latest)
        if latest_key and latest_key != before_key:
            if latest_status in success_statuses:
                return f"deployment={latest_key} status={latest_status}"
            if latest_status in failure_statuses:
                raise click.ClickException(f"{failure_message_prefix}: deployment={latest_key} status={latest_status}")
            if not latest_status:
                return f"deployment={latest_key} status=unknown"
        time.sleep(3)

    raise click.ClickException("Timed out waiting for Dokploy deployment status.")


def resolve_dokploy_target(
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
            compose_id, compose_name = resolve_dokploy_compose_id(
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
            application_id, app_name = resolve_dokploy_application_id(
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


def dokploy_status_payload(
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
        host, token = read_dokploy_config(environment_values)
    except click.ClickException as error:
        payload["error"] = error.message
        return payload

    ship_mode = resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    payload["ship_mode"] = ship_mode

    (
        target_type,
        target_id,
        target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = resolve_dokploy_target(
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
        compose_payload = dokploy_request(
            host=host,
            token=token,
            path="/api/compose.one",
            query={"composeId": target_id},
        )
        compose_payload_as_object = as_json_object(compose_payload)
        if compose_payload_as_object is not None:
            payload["compose_status"] = compose_payload_as_object.get("composeStatus")
            payload["source_type"] = compose_payload_as_object.get("sourceType")
            payload["server_id"] = compose_payload_as_object.get("serverId")
            payload["app_name"] = compose_payload_as_object.get("appName")
        payload["latest_deployment"] = summarize_deployment(latest_deployment_for_compose(host, token, target_id))
        return payload

    payload["latest_deployment"] = summarize_deployment(latest_deployment_for_application(host, token, target_id))
    return payload


def resolve_dokploy_target_for_command(
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
        compose_id, compose_name = resolve_dokploy_compose_id(
            host=host,
            token=token,
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )
        return "compose", compose_id, compose_name

    if normalized_target_type == "application":
        application_id, app_name = resolve_dokploy_application_id(
            host=host,
            token=token,
            context_name=context_name,
            instance_name=instance_name,
            environment_values=environment_values,
        )
        return "application", application_id, app_name

    ship_mode = resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    (
        selected_target_type,
        selected_target_id,
        selected_target_name,
        compose_resolution_error,
        app_resolution_error,
    ) = resolve_dokploy_target(
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


def parse_dokploy_env_text(raw_env_text: str) -> dict[str, str]:
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


def serialize_dokploy_env_text(env_map: dict[str, str]) -> str:
    if not env_map:
        return ""
    rendered_lines = [f"{env_key}={env_value}" for env_key, env_value in env_map.items()]
    return "\n".join(rendered_lines)


def fetch_dokploy_target_payload(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
) -> JsonObject:
    if target_type == "compose":
        payload = dokploy_request(
            host=host,
            token=token,
            path="/api/compose.one",
            query={"composeId": target_id},
        )
    elif target_type == "application":
        payload = dokploy_request(
            host=host,
            token=token,
            path="/api/application.one",
            query={"applicationId": target_id},
        )
    else:
        raise click.ClickException(f"Unsupported target type: {target_type}")

    payload_as_object = as_json_object(payload)
    if payload_as_object is None:
        raise click.ClickException(f"Dokploy {target_type}.one returned an invalid response payload.")
    return payload_as_object


def update_dokploy_target_env(
    *,
    host: str,
    token: str,
    target_type: str,
    target_id: str,
    target_payload: JsonObject,
    env_text: str,
) -> None:
    if target_type == "compose":
        dokploy_request(
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
        payload: JsonObject = {
            "applicationId": target_id,
            "env": env_text,
            "createEnvFile": bool(create_env_file) if isinstance(create_env_file, bool) else True,
        }
        if isinstance(build_args, str):
            payload["buildArgs"] = build_args
        if isinstance(build_secrets, str):
            payload["buildSecrets"] = build_secrets
        dokploy_request(
            host=host,
            token=token,
            path="/api/application.saveEnvironment",
            method="POST",
            payload=payload,
        )
        return

    raise click.ClickException(f"Unsupported target type: {target_type}")


def collect_rollback_ids(payload: JsonValue | list[JsonObject]) -> list[str]:
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


def wait_for_dokploy_deployment(
    *,
    host: str,
    token: str,
    application_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    return _wait_for_deployment_status(
        fetch_latest_deployment=lambda: latest_deployment_for_application(host, token, application_id),
        before_key=before_key,
        timeout_seconds=timeout_seconds,
        failure_message_prefix="Dokploy deployment failed",
    )


def wait_for_dokploy_compose_deployment(
    *,
    host: str,
    token: str,
    compose_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    return _wait_for_deployment_status(
        fetch_latest_deployment=lambda: latest_deployment_for_compose(host, token, compose_id),
        before_key=before_key,
        timeout_seconds=timeout_seconds,
        failure_message_prefix="Dokploy compose deployment failed",
    )


def resolve_ship_timeout_seconds(
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


def resolve_ship_health_timeout_seconds(
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


def normalize_healthcheck_path(raw_healthcheck_path: str) -> str:
    normalized_path = raw_healthcheck_path.strip() or DEFAULT_DOKPLOY_HEALTHCHECK_PATH
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return normalized_path


def resolve_healthcheck_base_urls(
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


def resolve_ship_healthcheck_urls(
    *,
    target_definition: DokployTargetDefinition | None,
    environment_values: dict[str, str],
) -> tuple[str, ...]:
    if target_definition is not None and not target_definition.healthcheck_enabled:
        return ()

    healthcheck_path = normalize_healthcheck_path(
        target_definition.healthcheck_path if target_definition is not None else DEFAULT_DOKPLOY_HEALTHCHECK_PATH
    )
    base_urls = resolve_healthcheck_base_urls(target_definition=target_definition, environment_values=environment_values)
    return tuple(f"{base_url}{healthcheck_path}" for base_url in base_urls)


def wait_for_ship_healthcheck(*, url: str, timeout_seconds: int) -> str:
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


def verify_ship_healthchecks(*, urls: tuple[str, ...], timeout_seconds: int) -> None:
    for healthcheck_url in urls:
        click.echo(f"healthcheck_url={healthcheck_url}")
        result = wait_for_ship_healthcheck(url=healthcheck_url, timeout_seconds=timeout_seconds)
        click.echo(f"healthcheck_result={result}")


def resolve_dokploy_source_file(repo_root: Path, source_file: Path | None) -> Path:
    resolved_source_file = source_file if source_file is not None else (repo_root / "platform" / "dokploy.toml")
    if not resolved_source_file.is_absolute():
        resolved_source_file = repo_root / resolved_source_file
    if not resolved_source_file.exists():
        raise click.ClickException(f"Dokploy source-of-truth file not found: {resolved_source_file}")
    return resolved_source_file


def load_dokploy_source_of_truth_if_present(
    repo_root: Path,
    load_dokploy_source_of_truth: Callable[[Path], DokploySourceOfTruth],
) -> DokploySourceOfTruth | None:
    source_file_path = repo_root / "platform" / "dokploy.toml"
    if not source_file_path.exists():
        return None
    return load_dokploy_source_of_truth(source_file_path)


def find_dokploy_target_definition(
    source_of_truth: DokploySourceOfTruth,
    *,
    context_name: str,
    instance_name: str,
) -> DokployTargetDefinition | None:
    for target in source_of_truth.targets:
        if target.context == context_name and target.instance == instance_name:
            return target
    return None


def collect_dokploy_deploy_servers(*, host: str, token: str) -> tuple[JsonObject, ...]:
    payload = dokploy_request(host=host, token=token, path="/api/server.all")
    server_items: list[JsonValue]
    if isinstance(payload, list):
        server_items = payload
    elif isinstance(payload, dict):
        for key_name in ("data", "items", "result", "servers"):
            nested_items = payload.get(key_name)
            if isinstance(nested_items, list):
                server_items = nested_items
                break
        else:
            raise click.ClickException("Dokploy server.all returned an invalid response payload.")
    else:
        raise click.ClickException("Dokploy server.all returned an invalid response payload.")

    deploy_servers: list[JsonObject] = []
    for entry in server_items:
        server_entry = as_json_object(entry)
        if server_entry is None:
            continue
        if str(server_entry.get("serverType") or "").strip().lower() != "deploy":
            continue
        deploy_servers.append(server_entry)
    return tuple(deploy_servers)


def resolve_dokploy_compose_remote_config(
    *,
    host: str,
    token: str,
    compose_name: str,
    environment_values: dict[str, str],
) -> tuple[Path, str]:
    """Resolve (remote_stack_path, compose_project_name) for a Dokploy compose target.

    The remote stack path is /etc/dokploy/applications/<appName> by default.
    The compose project name is the Dokploy appName (what Dokploy passes via -p).

    Override either value with env vars:
      DOKPLOY_REMOTE_STACK_PATH_<COMPOSE_NAME_UPPER>  e.g. DOKPLOY_REMOTE_STACK_PATH_CM_DEV
      DOKPLOY_COMPOSE_PROJECT_<COMPOSE_NAME_UPPER>    e.g. DOKPLOY_COMPOSE_PROJECT_CM_DEV
    """
    safe_name = compose_name.upper().replace("-", "_")
    path_override_key = f"DOKPLOY_REMOTE_STACK_PATH_{safe_name}"
    project_override_key = f"DOKPLOY_COMPOSE_PROJECT_{safe_name}"
    compose_id_override_key = f"DOKPLOY_COMPOSE_ID_{safe_name}"

    path_override = environment_values.get(path_override_key, "").strip()
    project_override = environment_values.get(project_override_key, "").strip()
    compose_id_override = environment_values.get(compose_id_override_key, "").strip()

    if path_override and project_override and compose_id_override:
        return Path(path_override), project_override

    projects_payload = dokploy_request(host=host, token=token, path="/api/project.all")
    records = collect_compose_records(projects_payload)
    matches = [record for record in records if record.get("compose_name") == compose_name]
    if not matches:
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
            f"Dokploy compose '{compose_name}' not found for remote path resolution. "
            f"Known: {preview}. "
            f"Set {compose_id_override_key}=<compose-id>, {path_override_key}=<path>, and "
            f"{project_override_key}=<project> to provide overrides."
        )

    match_ids = {
        record_compose_id
        for record in matches
        for record_compose_id in (record.get("compose_id"),)
        if isinstance(record_compose_id, str) and record_compose_id
    }
    if compose_id_override:
        if compose_id_override not in match_ids:
            known_match_ids = ", ".join(sorted(match_ids)) or "<none>"
            raise click.ClickException(
                f"Dokploy compose override {compose_id_override_key}={compose_id_override!r} does not match "
                f"compose '{compose_name}'. Matching ids: {known_match_ids}."
            )
        matches = [record for record in matches if record.get("compose_id") == compose_id_override]
        match_ids = {compose_id_override}

    if len(match_ids) > 1:
        known_match_ids = ", ".join(sorted(match_ids))
        raise click.ClickException(
            f"Dokploy compose name '{compose_name}' is ambiguous across multiple targets: {known_match_ids}. "
            f"Set {compose_id_override_key}=<compose-id> to disambiguate, plus {path_override_key} / "
            f"{project_override_key} if needed."
        )

    compose_id = matches[0].get("compose_id")
    if not isinstance(compose_id, str) or not compose_id:
        raise click.ClickException(
            f"Dokploy compose '{compose_name}' has no valid compose_id. "
            f"Set {compose_id_override_key}=<compose-id>, {path_override_key}=<path>, and "
            f"{project_override_key}=<project> to provide overrides."
        )

    compose_payload = dokploy_request(
        host=host,
        token=token,
        path="/api/compose.one",
        query={"composeId": compose_id},
    )
    compose_as_object = as_json_object(compose_payload)
    if compose_as_object is None:
        raise click.ClickException(
            f"Dokploy compose.one returned an invalid response for {compose_id}. "
            f"Set {compose_id_override_key}=<compose-id>, {path_override_key}=<path>, and "
            f"{project_override_key}=<project> to provide overrides."
        )

    app_name = compose_as_object.get("appName")
    if not isinstance(app_name, str) or not app_name:
        raise click.ClickException(
            f"Dokploy compose {compose_id} has no appName in API response. "
            f"Set {compose_id_override_key}=<compose-id>, {path_override_key}=<path>, and "
            f"{project_override_key}=<project> to provide overrides."
        )

    resolved_path = Path(path_override) if path_override else Path("/etc/dokploy/applications") / app_name
    resolved_project = project_override if project_override else app_name
    return resolved_path, resolved_project
