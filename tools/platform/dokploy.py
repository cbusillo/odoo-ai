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
    timeout_seconds: int | float = 60,
) -> JsonValue:
    normalized_host = host.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{normalized_host}{normalized_path}"
    headers = {"x-api-key": token}
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=payload,
            params=query,
            timeout=timeout_seconds,
        )
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
            "Missing DOKPLOY_HOST or DOKPLOY_TOKEN in resolved environment (selected env file and/or platform/secrets.toml)."
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


def extract_schedules(raw_payload: JsonValue) -> list[JsonObject]:
    if isinstance(raw_payload, list):
        schedule_items: list[JsonObject] = []
        for item in raw_payload:
            item_as_object = as_json_object(item)
            if item_as_object is not None:
                schedule_items.append(item_as_object)
        return schedule_items
    if isinstance(raw_payload, dict):
        for key in ("data", "schedules", "items", "result"):
            value = raw_payload.get(key)
            if isinstance(value, list):
                schedule_items: list[JsonObject] = []
                for item in value:
                    item_as_object = as_json_object(item)
                    if item_as_object is not None:
                        schedule_items.append(item_as_object)
                return schedule_items
    return []


def schedule_key(schedule: JsonObject) -> str:
    for key in ("scheduleId", "schedule_id", "id", "uuid"):
        value = schedule.get(key)
        if value:
            return str(value)
    return ""


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


def resolve_dokploy_ship_mode(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_SHIP_MODE_{context_name}_{instance_name}".upper()
    configured_mode = environment_values.get(specific_key, "").strip().lower()
    if not configured_mode:
        configured_mode = environment_values.get("DOKPLOY_SHIP_MODE", "auto").strip().lower() or "auto"
    if configured_mode not in {"auto", "compose", "application"}:
        raise click.ClickException(f"Invalid Dokploy ship mode '{configured_mode}'. Expected auto, compose, or application.")
    return configured_mode


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


def latest_deployment_for_schedule(host: str, token: str, schedule_id: str) -> JsonObject | None:
    payload = dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.allByType",
        query={"id": schedule_id, "type": "schedule"},
    )
    deployments = extract_deployments(payload)
    return _latest_deployment_from_list(deployments)


def wait_for_dokploy_schedule_deployment(
    *,
    host: str,
    token: str,
    schedule_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    return _wait_for_deployment_status(
        fetch_latest_deployment=lambda: latest_deployment_for_schedule(host, token, schedule_id),
        before_key=before_key,
        timeout_seconds=timeout_seconds,
        failure_message_prefix="Dokploy schedule deployment failed",
    )


def resolve_dokploy_user_id(*, host: str, token: str) -> str:
    payload = dokploy_request(host=host, token=token, path="/api/user.session")
    payload_as_object = as_json_object(payload)
    if payload_as_object is None:
        raise click.ClickException("Dokploy user.session returned an invalid response payload.")
    user_payload = as_json_object(payload_as_object.get("user"))
    if user_payload is None:
        raise click.ClickException("Dokploy user.session returned no user payload.")
    user_id = str(user_payload.get("id") or "").strip()
    if not user_id:
        raise click.ClickException("Dokploy user.session returned no user id.")
    return user_id


def list_dokploy_schedules(
    *,
    host: str,
    token: str,
    target_id: str,
    schedule_type: str,
) -> tuple[JsonObject, ...]:
    payload = dokploy_request(
        host=host,
        token=token,
        path="/api/schedule.list",
        query={"id": target_id, "scheduleType": schedule_type},
    )
    return tuple(extract_schedules(payload))


def find_matching_dokploy_schedule(
    *,
    host: str,
    token: str,
    target_id: str,
    schedule_type: str,
    schedule_name: str,
    app_name: str,
) -> JsonObject | None:
    for schedule in list_dokploy_schedules(
        host=host,
        token=token,
        target_id=target_id,
        schedule_type=schedule_type,
    ):
        if str(schedule.get("name") or "").strip() != schedule_name:
            continue
        if str(schedule.get("appName") or "").strip() != app_name:
            continue
        return schedule
    return None


def upsert_dokploy_schedule(
    *,
    host: str,
    token: str,
    target_id: str,
    schedule_type: str,
    schedule_name: str,
    app_name: str,
    schedule_payload: JsonObject,
) -> JsonObject:
    existing_schedule = find_matching_dokploy_schedule(
        host=host,
        token=token,
        target_id=target_id,
        schedule_type=schedule_type,
        schedule_name=schedule_name,
        app_name=app_name,
    )

    if existing_schedule is not None:
        updated_payload = dict(schedule_payload)
        updated_payload["scheduleId"] = schedule_key(existing_schedule)
        dokploy_request(
            host=host,
            token=token,
            path="/api/schedule.update",
            method="POST",
            payload=updated_payload,
        )
    else:
        dokploy_request(
            host=host,
            token=token,
            path="/api/schedule.create",
            method="POST",
            payload=schedule_payload,
        )

    resolved_schedule = find_matching_dokploy_schedule(
        host=host,
        token=token,
        target_id=target_id,
        schedule_type=schedule_type,
        schedule_name=schedule_name,
        app_name=app_name,
    )
    if resolved_schedule is None:
        raise click.ClickException(
            f"Dokploy schedule {schedule_name!r} for {schedule_type} target {target_id!r} could not be resolved after upsert."
        )
    return resolved_schedule


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


def _resolve_configured_target_reference(
    *,
    context_name: str,
    instance_name: str,
    requested_target_type: str,
    target_definition: DokployTargetDefinition | None,
) -> tuple[str, str, str] | None:
    if target_definition is None:
        return None

    configured_target_id = target_definition.target_id.strip()
    if not configured_target_id:
        return None

    configured_target_type = target_definition.target_type.strip().lower()
    if requested_target_type != "auto" and requested_target_type != configured_target_type:
        raise click.ClickException(
            "Dokploy target-type override conflicts with platform/dokploy.toml. "
            f"Target {context_name}/{instance_name} is configured as '{configured_target_type}', "
            f"but the command requested '{requested_target_type}'."
        )

    configured_target_name = target_definition.target_name.strip() or f"{context_name}-{instance_name}"
    return configured_target_type, configured_target_id, configured_target_name


def resolve_dokploy_target(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    ship_mode: str,
    target_definition: DokployTargetDefinition | None = None,
) -> tuple[str, str, str, click.ClickException | None, click.ClickException | None]:
    _ = host, token, environment_values
    configured_target = _resolve_configured_target_reference(
        context_name=context_name,
        instance_name=instance_name,
        requested_target_type=ship_mode,
        target_definition=target_definition,
    )
    if configured_target is None:
        return (
            "",
            "",
            "",
            click.ClickException(
                "No Dokploy target is configured for "
                f"{context_name}/{instance_name}. Define it in platform/dokploy.toml with target_type and target_id."
            ),
            None,
        )

    configured_target_type, configured_target_id, configured_target_name = configured_target
    return configured_target_type, configured_target_id, configured_target_name, None, None


def dokploy_status_payload(
    *,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    target_definition: DokployTargetDefinition | None = None,
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
        target_definition=target_definition,
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
    target_definition: DokployTargetDefinition | None = None,
) -> tuple[str, str, str]:
    _ = host, token, environment_values
    normalized_target_type = target_type.strip().lower()
    if normalized_target_type not in {"auto", "compose", "application"}:
        raise click.ClickException("target-type must be one of: auto, compose, application.")

    configured_target = _resolve_configured_target_reference(
        context_name=context_name,
        instance_name=instance_name,
        requested_target_type=normalized_target_type,
        target_definition=target_definition,
    )
    if configured_target is not None:
        return configured_target
    raise click.ClickException(
        "No Dokploy target is configured for "
        f"{context_name}/{instance_name}. Define it in platform/dokploy.toml with target_type and target_id."
    )


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
