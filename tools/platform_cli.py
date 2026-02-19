from __future__ import annotations

import json
import os
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import click
import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
type JsonObject = dict[str, JsonValue]


class ContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    install_modules: tuple[str, ...] = ()
    update_modules: str = "AUTO"
    instances: dict[str, "InstanceDefinition"] = Field(default_factory=dict)


class InstanceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str | None = None
    install_modules_add: tuple[str, ...] = ()


class StackDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    odoo_version: str
    state_root: str
    addons_path: tuple[str, ...]
    required_env_keys: tuple[str, ...] = ()
    contexts: dict[str, ContextDefinition]


@dataclass(frozen=True)
class LoadedStack:
    stack_file_path: Path
    stack_definition: StackDefinition


@dataclass(frozen=True)
class RuntimeSelection:
    context_name: str
    instance_name: str
    context_definition: ContextDefinition
    instance_definition: InstanceDefinition
    database_name: str
    project_name: str
    state_path: Path
    data_mount: Path
    runtime_conf_host_path: Path
    data_volume_name: str
    log_volume_name: str
    db_volume_name: str
    web_host_port: int
    longpoll_host_port: int
    db_host_port: int
    runtime_odoo_conf_path: str
    effective_install_modules: tuple[str, ...]


def _discover_repo_root(start_directory: Path) -> Path:
    current_directory = start_directory.resolve()
    for candidate_path in (current_directory, *current_directory.parents):
        if (candidate_path / ".git").exists() or (candidate_path / "pyproject.toml").exists():
            return candidate_path
    return current_directory


def _parse_env_file(env_file_path: Path) -> dict[str, str]:
    parsed_values: dict[str, str] = {}
    for raw_line in env_file_path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if "=" not in stripped_line:
            continue
        key_part, value_part = stripped_line.split("=", 1)
        environment_key = key_part.strip()
        environment_value = value_part.strip()
        if len(environment_value) >= 2 and environment_value[0] == environment_value[-1] and environment_value[0] in {'"', "'"}:
            environment_value = environment_value[1:-1]
        if " #" in environment_value:
            environment_value = environment_value.split(" #", 1)[0].rstrip()
        parsed_values[environment_key] = environment_value
    return parsed_values


def _load_environment(repo_root: Path, env_file: Path | None) -> tuple[Path, dict[str, str]]:
    env_file_path = env_file if env_file is not None else _resolve_default_env_file(repo_root)
    if not env_file_path.is_absolute():
        env_file_path = repo_root / env_file_path
    if not env_file_path.exists():
        raise click.ClickException(f"Env file not found: {env_file_path}")
    return env_file_path, _parse_env_file(env_file_path)


def _load_stack(stack_file_path: Path) -> LoadedStack:
    loaded_data = tomllib.loads(stack_file_path.read_text(encoding="utf-8"))
    try:
        stack_definition = StackDefinition.model_validate(loaded_data)
    except ValidationError as error:
        message = error.json(indent=2)
        raise click.ClickException(f"Invalid stack file: {stack_file_path}\n{message}") from error
    return LoadedStack(stack_file_path=stack_file_path, stack_definition=stack_definition)


def _resolve_default_env_file(repo_root: Path) -> Path:
    root_env_file = repo_root / ".env"
    if root_env_file.exists():
        return root_env_file
    platform_env_file = repo_root / "platform" / ".env"
    if platform_env_file.exists():
        return platform_env_file
    return root_env_file


def _merge_effective_modules(context_definition: ContextDefinition, instance_definition: InstanceDefinition) -> tuple[str, ...]:
    effective_install_modules: list[str] = []
    for module_name in context_definition.install_modules:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    for module_name in instance_definition.install_modules_add:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    return tuple(effective_install_modules)


def _port_seed_for_context(context_name: str) -> tuple[int, int, int]:
    context_port_map = {
        "opw": (8069, 8072, 15432),
        "cm": (9069, 9072, 25432),
        "qc": (10069, 10072, 35432),
    }
    return context_port_map.get(context_name, (11069, 11072, 45432))


def _port_offset_for_instance(instance_name: str) -> int:
    instance_offset_map = {
        "local": 0,
        "dev": 100,
        "testing": 200,
        "prod": 300,
    }
    return instance_offset_map.get(instance_name, 0)


def _resolve_runtime_selection(stack_definition: StackDefinition, context_name: str, instance_name: str) -> RuntimeSelection:
    if context_name not in stack_definition.contexts:
        available_contexts = ", ".join(sorted(stack_definition.contexts))
        raise click.ClickException(f"Unknown context '{context_name}'. Available: {available_contexts}")

    context_definition = stack_definition.contexts[context_name]
    instance_definition = context_definition.instances.get(instance_name, InstanceDefinition())
    database_name = instance_definition.database or context_name
    effective_install_modules = _merge_effective_modules(context_definition, instance_definition)

    base_web_port, base_longpoll_port, base_db_port = _port_seed_for_context(context_name)
    instance_offset = _port_offset_for_instance(instance_name)
    web_host_port = base_web_port + instance_offset
    longpoll_host_port = base_longpoll_port + instance_offset
    db_host_port = base_db_port + instance_offset

    expanded_state_root = os.path.expanduser(stack_definition.state_root)
    state_path = Path(expanded_state_root) / f"{context_name}-{instance_name}"
    data_volume_name = f"odoo-{context_name}-{instance_name}-data"
    log_volume_name = f"odoo-{context_name}-{instance_name}-logs"
    db_volume_name = f"odoo-{context_name}-{instance_name}-db"

    return RuntimeSelection(
        context_name=context_name,
        instance_name=instance_name,
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name=database_name,
        project_name=f"odoo-{context_name}-{instance_name}",
        state_path=state_path,
        data_mount=state_path / "data",
        runtime_conf_host_path=state_path / "data" / "platform.odoo.conf",
        data_volume_name=data_volume_name,
        log_volume_name=log_volume_name,
        db_volume_name=db_volume_name,
        web_host_port=web_host_port,
        longpoll_host_port=longpoll_host_port,
        db_host_port=db_host_port,
        runtime_odoo_conf_path="/volumes/data/platform.odoo.conf",
        effective_install_modules=effective_install_modules,
    )


def _write_runtime_odoo_conf_file(
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    runtime_selection.runtime_conf_host_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_conf_file = runtime_selection.runtime_conf_host_path

    lines: list[str] = ["[options]"]
    lines.append(f"db_name = {runtime_selection.database_name}")
    lines.append(f"db_user = {source_environment.get('ODOO_DB_USER', 'odoo')}")
    lines.append(f"db_password = {source_environment.get('ODOO_DB_PASSWORD', '')}")
    lines.append("db_host = database")
    lines.append("db_port = 5432")
    lines.append("list_db = False")
    lines.append(f"addons_path = {','.join(stack_definition.addons_path)}")
    lines.append("data_dir = /volumes/data")
    lines.append("")
    lines.append(f"; context={runtime_selection.context_name}")
    lines.append(f"; instance={runtime_selection.instance_name}")
    lines.append(f"; install_modules={','.join(runtime_selection.effective_install_modules)}")

    runtime_conf_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_conf_file


def _write_runtime_env_file(repo_root: Path, runtime_selection: RuntimeSelection, source_environment: dict[str, str]) -> Path:
    runtime_env_directory = repo_root / ".platform" / "env"
    runtime_env_directory.mkdir(parents=True, exist_ok=True)
    runtime_env_file = runtime_env_directory / f"{runtime_selection.context_name}.{runtime_selection.instance_name}.env"

    runtime_selection.runtime_conf_host_path.parent.mkdir(parents=True, exist_ok=True)

    runtime_values = {
        "ODOO_PROJECT_NAME": runtime_selection.project_name,
        "ODOO_STATE_ROOT": str(runtime_selection.state_path),
        "ODOO_RUNTIME_CONF_HOST_PATH": str(runtime_selection.runtime_conf_host_path),
        "ODOO_DATA_VOLUME": runtime_selection.data_volume_name,
        "ODOO_LOG_VOLUME": runtime_selection.log_volume_name,
        "ODOO_DB_VOLUME": runtime_selection.db_volume_name,
        "ODOO_DB_NAME": runtime_selection.database_name,
        "ODOO_DB_USER": source_environment.get("ODOO_DB_USER", "odoo"),
        "ODOO_DB_PASSWORD": source_environment.get("ODOO_DB_PASSWORD", ""),
        "ODOO_MASTER_PASSWORD": source_environment.get("ODOO_MASTER_PASSWORD", ""),
        "ODOO_INSTALL_MODULES": ",".join(runtime_selection.effective_install_modules),
        "ODOO_UPDATE_MODULES": runtime_selection.context_definition.update_modules,
        "ODOO_ADDONS_PATH": ",".join(("/opt/project/addons", "/opt/extra_addons", "/odoo/addons")),
        "ODOO_WEB_HOST_PORT": str(runtime_selection.web_host_port),
        "ODOO_LONGPOLL_HOST_PORT": str(runtime_selection.longpoll_host_port),
        "ODOO_DB_HOST_PORT": str(runtime_selection.db_host_port),
        "ODOO_LIST_DB": "False",
        "ODOO_WEB_COMMAND": f"python3 /volumes/scripts/run_odoo_bootstrap.py -c {runtime_selection.runtime_odoo_conf_path}",
        "RESTORE_SSH_DIR": source_environment.get("RESTORE_SSH_DIR", str(Path.home() / ".ssh")),
    }

    lines = [f"{key}={value}" for key, value in runtime_values.items()]
    runtime_env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_env_file


def _compose_base_command(runtime_env_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(runtime_env_file),
        "-f",
        "docker-compose.yml",
        "-f",
        "docker/config/base.yaml",
        "-f",
        "docker-compose.override.yml",
    ]


def _run_command(command: list[str]) -> None:
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        joined_command = " ".join(command)
        raise click.ClickException(f"Command failed ({result.returncode}): {joined_command}")


def _dokploy_request(
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
    response = requests.request(method, url, headers=headers, json=payload, params=query, timeout=60)
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


def _read_dokploy_config(environment_values: dict[str, str]) -> tuple[str, str]:
    host = environment_values.get("DOKPLOY_HOST", "").strip()
    token = environment_values.get("DOKPLOY_TOKEN", "").strip()
    if not host or not token:
        raise click.ClickException("Missing DOKPLOY_HOST or DOKPLOY_TOKEN in .env.")
    return host, token


def _as_json_object(value: JsonValue) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return cast(JsonObject, value)


def _extract_deployments(raw_payload: JsonValue) -> list[JsonObject]:
    if isinstance(raw_payload, list):
        deployment_items: list[JsonObject] = []
        for item in raw_payload:
            item_as_object = _as_json_object(item)
            if item_as_object is not None:
                deployment_items.append(item_as_object)
        return deployment_items
    if isinstance(raw_payload, dict):
        for key in ("data", "deployments", "items", "result"):
            value = raw_payload.get(key)
            if isinstance(value, list):
                deployment_items = []
                for item in value:
                    item_as_object = _as_json_object(item)
                    if item_as_object is not None:
                        deployment_items.append(item_as_object)
                return deployment_items
    return []


def _deployment_key(deployment: JsonObject) -> str:
    for key in ("deploymentId", "deployment_id", "id", "uuid"):
        value = deployment.get(key)
        if value:
            return str(value)
    return ""


def _deployment_status(deployment: JsonObject) -> str:
    for key in ("status", "state", "deploymentStatus"):
        value = deployment.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def _collect_application_records(payload: JsonValue) -> list[JsonObject]:
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


def _resolve_dokploy_app_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_APP_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def _resolve_dokploy_compose_name(context_name: str, instance_name: str, environment_values: dict[str, str]) -> str:
    specific_key = f"DOKPLOY_COMPOSE_NAME_{context_name}_{instance_name}".upper()
    specific_value = environment_values.get(specific_key, "").strip()
    if specific_value:
        return specific_value
    return f"{context_name}-{instance_name}"


def _collect_compose_records(payload: JsonValue) -> list[JsonObject]:
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


def _resolve_dokploy_compose_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_COMPOSE_ID_{context_name}_{instance_name}".upper()
    explicit_compose_id = environment_values.get(specific_id_key, "").strip()
    compose_name = _resolve_dokploy_compose_name(context_name, instance_name, environment_values)
    if explicit_compose_id:
        return explicit_compose_id, compose_name

    projects_payload = _dokploy_request(host=host, token=token, path="/api/project.all")
    records = _collect_compose_records(projects_payload)
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


def _resolve_dokploy_ship_mode(
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> str:
    specific_key = f"DOKPLOY_SHIP_MODE_{context_name}_{instance_name}".upper()
    configured_mode = environment_values.get(specific_key, "").strip().lower()
    if not configured_mode:
        configured_mode = environment_values.get("DOKPLOY_SHIP_MODE", "auto").strip().lower() or "auto"
    if configured_mode not in {"auto", "compose", "application"}:
        raise click.ClickException(
            f"Invalid Dokploy ship mode '{configured_mode}'. Expected auto, compose, or application."
        )
    return configured_mode


def _resolve_dokploy_application_id(
    *,
    host: str,
    token: str,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
) -> tuple[str, str]:
    specific_id_key = f"DOKPLOY_APPLICATION_ID_{context_name}_{instance_name}".upper()
    explicit_application_id = environment_values.get(specific_id_key, "").strip()
    app_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
    if explicit_application_id:
        return explicit_application_id, app_name

    projects_payload = _dokploy_request(host=host, token=token, path="/api/project.all")
    records = _collect_application_records(projects_payload)
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


def _latest_deployment_for_application(host: str, token: str, application_id: str) -> JsonObject | None:
    payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = _extract_deployments(payload)
    if not deployments:
        return None

    def sort_key(item: JsonObject) -> str:
        for key in ("createdAt", "created_at", "updatedAt", "updated_at"):
            value = item.get(key)
            if value:
                return str(value)
        return _deployment_key(item)

    return max(deployments, key=sort_key)


def _latest_deployment_for_compose(host: str, token: str, compose_id: str) -> JsonObject | None:
    compose_payload = _dokploy_request(
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
    for item in deployments_payload:
        item_as_object = _as_json_object(cast(JsonValue, item))
        if item_as_object is not None:
            deployments.append(item_as_object)
    if not deployments:
        return None

    def sort_key(item: JsonObject) -> str:
        for key in ("createdAt", "created_at", "updatedAt", "updated_at"):
            value = item.get(key)
            if value:
                return str(value)
        return _deployment_key(item)

    return max(deployments, key=sort_key)


def _collect_rollback_ids(payload: JsonValue | list[JsonObject]) -> list[str]:
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


def _wait_for_dokploy_deployment(
    *,
    host: str,
    token: str,
    application_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    success_statuses = {"success", "succeeded", "done", "completed", "healthy", "finished"}
    failure_statuses = {"failed", "error", "canceled", "cancelled", "killed", "unhealthy", "timeout"}

    start_time = time.monotonic()
    while time.monotonic() - start_time <= timeout_seconds:
        latest = _latest_deployment_for_application(host, token, application_id)
        if not latest:
            time.sleep(3)
            continue

        latest_key = _deployment_key(latest)
        latest_status = _deployment_status(latest)
        if latest_key and latest_key != before_key:
            if latest_status in success_statuses:
                return f"deployment={latest_key} status={latest_status}"
            if latest_status in failure_statuses:
                raise click.ClickException(f"Dokploy deployment failed: deployment={latest_key} status={latest_status}")
            if not latest_status:
                return f"deployment={latest_key} status=unknown"
        time.sleep(3)

    raise click.ClickException("Timed out waiting for Dokploy deployment status.")


def _wait_for_dokploy_compose_deployment(
    *,
    host: str,
    token: str,
    compose_id: str,
    before_key: str,
    timeout_seconds: int,
) -> str:
    success_statuses = {"success", "succeeded", "done", "completed", "healthy", "finished"}
    failure_statuses = {"failed", "error", "canceled", "cancelled", "killed", "unhealthy", "timeout"}

    start_time = time.monotonic()
    while time.monotonic() - start_time <= timeout_seconds:
        latest = _latest_deployment_for_compose(host, token, compose_id)
        if not latest:
            time.sleep(3)
            continue

        latest_key = _deployment_key(latest)
        latest_status = _deployment_status(latest)
        if latest_key and latest_key != before_key:
            if latest_status in success_statuses:
                return f"deployment={latest_key} status={latest_status}"
            if latest_status in failure_statuses:
                raise click.ClickException(f"Dokploy compose deployment failed: deployment={latest_key} status={latest_status}")
            if not latest_status:
                return f"deployment={latest_key} status=unknown"
        time.sleep(3)

    raise click.ClickException("Timed out waiting for Dokploy compose deployment status.")


def _render_odoo_config(
    *,
    stack_definition: StackDefinition,
    context_name: str,
    instance_name: str,
    environment_values: dict[str, str],
    include_comments: bool,
) -> str:
    runtime_selection = _resolve_runtime_selection(stack_definition, context_name, instance_name)

    lines: list[str] = ["[options]"]
    lines.append(f"db_name = {runtime_selection.database_name}")
    lines.append(f"db_user = {environment_values.get('ODOO_DB_USER', 'odoo')}")
    lines.append(f"db_password = {environment_values.get('ODOO_DB_PASSWORD', '')}")
    lines.append("db_host = database")
    lines.append("db_port = 5432")
    lines.append("list_db = False")
    lines.append(f"addons_path = {','.join(stack_definition.addons_path)}")
    lines.append(f"data_dir = {runtime_selection.data_mount}")

    if include_comments:
        lines.append("")
        lines.append(f"; context={context_name}")
        lines.append(f"; instance={instance_name}")
        lines.append(f"; install_modules={','.join(runtime_selection.effective_install_modules)}")
        lines.append(f"; update_modules={runtime_selection.context_definition.update_modules}")

    return "\n".join(lines) + "\n"


@click.group(help="Minimal platform contract CLI.")
def main() -> None:
    return None


@main.command("validate-config")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
def validate_config(stack_file: Path, env_file: Path | None) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    env_file_path, parsed_environment = _load_environment(repo_root, env_file)
    missing_keys: list[str] = []
    for required_key in loaded_stack.stack_definition.required_env_keys:
        if not parsed_environment.get(required_key):
            missing_keys.append(required_key)

    click.echo(f"stack_file={loaded_stack.stack_file_path}")
    click.echo(f"env_file={env_file_path}")
    click.echo(f"schema_version={loaded_stack.stack_definition.schema_version}")
    click.echo(f"contexts={','.join(sorted(loaded_stack.stack_definition.contexts))}")

    if missing_keys:
        formatted_missing_keys = ", ".join(missing_keys)
        raise click.ClickException(f"Missing required env keys: {formatted_missing_keys}")

    click.echo("validation=ok")


@main.command("list-contexts")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--json-output", is_flag=True, default=False)
def list_contexts(stack_file: Path, json_output: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    context_names = sorted(loaded_stack.stack_definition.contexts)

    if json_output:
        click.echo(json.dumps({"contexts": context_names}, indent=2))
        return

    for context_name in context_names:
        click.echo(context_name)


@main.command("render-odoo-conf")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    default=Path(".platform/odoo.conf"),
    show_default=True,
)
@click.option("--include-comments/--no-comments", default=True)
def render_odoo_conf(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    output_file: Path,
    include_comments: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    _env_file_path, loaded_environment = _load_environment(repo_root, env_file)

    loaded_stack = _load_stack(stack_file_path)
    rendered_config = _render_odoo_config(
        stack_definition=loaded_stack.stack_definition,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=loaded_environment,
        include_comments=include_comments,
    )

    output_file_path = output_file if output_file.is_absolute() else (repo_root / output_file)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(rendered_config, encoding="utf-8")
    click.echo(f"wrote={output_file_path}")


@main.command("doctor")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--json-output", is_flag=True, default=False)
def doctor(stack_file: Path, context_name: str, instance_name: str, json_output: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    payload = {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "project_name": runtime_selection.project_name,
        "state_path": str(runtime_selection.state_path),
        "runtime_conf_host_path": str(runtime_selection.runtime_conf_host_path),
        "data_volume": runtime_selection.data_volume_name,
        "log_volume": runtime_selection.log_volume_name,
        "db_volume": runtime_selection.db_volume_name,
        "web_host_port": runtime_selection.web_host_port,
        "longpoll_host_port": runtime_selection.longpoll_host_port,
        "db_host_port": runtime_selection.db_host_port,
        "install_modules": list(runtime_selection.effective_install_modules),
    }

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    for key, value in payload.items():
        click.echo(f"{key}={value}")


@main.command("up")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--build/--no-build", default=True)
def up(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None, build: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)

    _env_file_path, loaded_environment = _load_environment(repo_root, env_file)
    _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)

    runtime_env_file = _write_runtime_env_file(repo_root, runtime_selection, loaded_environment)
    compose_command = _compose_base_command(runtime_env_file)
    if build:
        _run_command(compose_command + ["build"])
    up_command = compose_command + ["up", "-d", "--no-build"]
    _run_command(up_command)
    click.echo(f"up={runtime_selection.project_name}")


@main.command("down")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--volumes", is_flag=True, default=False)
def down(context_name: str, instance_name: str, volumes: bool) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    compose_command = _compose_base_command(runtime_env_file)
    down_command = compose_command + ["down", "--remove-orphans"]
    if volumes:
        down_command.append("--volumes")
    _run_command(down_command)
    click.echo(f"down={context_name}-{instance_name}")


@main.command("logs")
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--service", default="web", show_default=True)
@click.option("--follow/--no-follow", default=True)
@click.option("--lines", default=200, show_default=True)
def logs(context_name: str, instance_name: str, service: str, follow: bool, lines: int) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    compose_command = _compose_base_command(runtime_env_file)
    log_command = compose_command + ["logs", "--tail", str(lines)]
    if follow:
        log_command.append("-f")
    log_command.append(service)
    _run_command(log_command)


def _compose_exec(runtime_env_file: Path, container_service: str, container_command: list[str]) -> None:
    compose_command = _compose_base_command(runtime_env_file)
    _run_command(compose_command + ["exec", "-T", container_service] + container_command)


@main.command("build")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
def build(stack_file: Path, context_name: str, instance_name: str, env_file: Path | None) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(repo_root, env_file)
    _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)
    runtime_env_file = _write_runtime_env_file(repo_root, runtime_selection, loaded_environment)

    compose_command = _compose_base_command(runtime_env_file)
    _run_command(compose_command + ["build"])
    click.echo(f"build={runtime_selection.project_name}")


@main.command("inspect")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--json-output", is_flag=True, default=False)
def inspect_context(
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    json_output: bool,
) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(repo_root, env_file)
    runtime_conf_file = _write_runtime_odoo_conf_file(runtime_selection, loaded_stack.stack_definition, loaded_environment)

    inspection_payload = {
        "context": runtime_selection.context_name,
        "instance": runtime_selection.instance_name,
        "database": runtime_selection.database_name,
        "odoo_conf_host": str(runtime_conf_file),
        "odoo_conf_container": runtime_selection.runtime_odoo_conf_path,
        "addons_path": list(loaded_stack.stack_definition.addons_path),
        "install_modules": list(runtime_selection.effective_install_modules),
        "note": "Use this context/instance pair in PyCharm run configs and inspections.",
    }

    if json_output:
        click.echo(json.dumps(inspection_payload, indent=2))
        return

    for key, value in inspection_payload.items():
        click.echo(f"{key}={value}")


@main.command("ship")
@click.option("--context", "context_name", required=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    required=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--wait/--no-wait", default=True)
@click.option("--timeout", "timeout_seconds", default=600, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def ship(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    wait: bool,
    timeout_seconds: int,
    dry_run: bool,
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Ship currently supports cm/opw contexts.")

    repo_root = _discover_repo_root(Path.cwd())
    _env_file_path, environment_values = _load_environment(repo_root, env_file)
    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    try:
        host, token = _read_dokploy_config(environment_values)
    except click.ClickException as error:
        if dry_run:
            target_name = _resolve_dokploy_compose_name(context_name, instance_name, environment_values)
            if ship_mode == "application":
                target_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
            click.echo(f"ship_mode=dokploy-{ship_mode}-api")
            click.echo(f"target_name={target_name}")
            click.echo(f"dry_run_note={error.message}")
            return
        raise

    compose_resolution_error: click.ClickException | None = None
    app_resolution_error: click.ClickException | None = None

    selected_target_type = ""
    selected_target_id = ""
    selected_target_name = ""

    if ship_mode in {"auto", "compose"}:
        try:
            compose_id, compose_name = _resolve_dokploy_compose_id(
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
            application_id, app_name = _resolve_dokploy_application_id(
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

    if not selected_target_type:
        messages = ["No Dokploy deployment target resolved."]
        if compose_resolution_error is not None:
            messages.append(f"compose_error={compose_resolution_error.message}")
        if app_resolution_error is not None:
            messages.append(f"application_error={app_resolution_error.message}")
        raise click.ClickException(" ".join(messages))

    if selected_target_type == "compose":
        latest_before = _latest_deployment_for_compose(host, token, selected_target_id)
        before_key = _deployment_key(latest_before or {})

        click.echo("ship_mode=dokploy-compose-api")
        click.echo(f"compose_name={selected_target_name}")
        click.echo(f"compose_id={selected_target_id}")
        if dry_run:
            return

        _dokploy_request(
            host=host,
            token=token,
            path="/api/compose.deploy",
            method="POST",
            payload={"composeId": selected_target_id},
        )
        click.echo("deploy_triggered=true")
        if not wait:
            return
        result = _wait_for_dokploy_compose_deployment(
            host=host,
            token=token,
            compose_id=selected_target_id,
            before_key=before_key,
            timeout_seconds=timeout_seconds,
        )
        click.echo(result)
        return

    latest_before = _latest_deployment_for_application(host, token, selected_target_id)
    before_key = _deployment_key(latest_before or {})

    click.echo(f"ship_mode=dokploy-api")
    click.echo(f"app_name={selected_target_name}")
    click.echo(f"application_id={selected_target_id}")
    if dry_run:
        return

    _dokploy_request(
        host=host,
        token=token,
        path="/api/application.deploy",
        method="POST",
        payload={"applicationId": selected_target_id},
    )
    click.echo("deploy_triggered=true")
    if not wait:
        return
    result = _wait_for_dokploy_deployment(
        host=host,
        token=token,
        application_id=selected_target_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )
    click.echo(result)


@main.command("rollback")
@click.option("--context", "context_name", required=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(("dev", "testing", "prod"), case_sensitive=False),
    required=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--rollback-id", default="", help="Explicit Dokploy rollback id")
@click.option("--list", "list_only", is_flag=True, default=False, help="List discovered rollback ids and exit")
@click.option("--wait/--no-wait", default=True)
@click.option("--timeout", "timeout_seconds", default=600, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def rollback(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    rollback_id: str,
    list_only: bool,
    wait: bool,
    timeout_seconds: int,
    dry_run: bool,
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Rollback currently supports cm/opw contexts.")

    repo_root = _discover_repo_root(Path.cwd())
    _env_file_path, environment_values = _load_environment(repo_root, env_file)
    ship_mode = _resolve_dokploy_ship_mode(context_name, instance_name, environment_values)
    if ship_mode == "compose":
        raise click.ClickException("Rollback in compose ship mode is not supported yet. Use Dokploy UI rollback controls.")
    try:
        host, token = _read_dokploy_config(environment_values)
    except click.ClickException as error:
        if dry_run:
            app_name = _resolve_dokploy_app_name(context_name, instance_name, environment_values)
            click.echo(f"app_name={app_name}")
            click.echo(f"dry_run_note={error.message}")
            return
        raise
    application_id, app_name = _resolve_dokploy_application_id(
        host=host,
        token=token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=environment_values,
    )

    deployment_payload = _dokploy_request(
        host=host,
        token=token,
        path="/api/deployment.all",
        query={"applicationId": application_id},
    )
    deployments = _extract_deployments(deployment_payload)
    discovered_rollback_ids = _collect_rollback_ids(deployments)

    click.echo(f"app_name={app_name}")
    click.echo(f"application_id={application_id}")

    if list_only:
        click.echo(json.dumps({"rollback_ids": discovered_rollback_ids}, indent=2))
        return

    selected_rollback_id = rollback_id.strip()
    if not selected_rollback_id:
        if not discovered_rollback_ids:
            raise click.ClickException(
                "No rollback ids discovered for this application. Pass --rollback-id explicitly or run --list."
            )
        selected_rollback_id = discovered_rollback_ids[0]

    latest_before = _latest_deployment_for_application(host, token, application_id)
    before_key = _deployment_key(latest_before or {})

    click.echo(f"rollback_id={selected_rollback_id}")
    if dry_run:
        return

    _dokploy_request(
        host=host,
        token=token,
        path="/api/rollback.rollback",
        method="POST",
        payload={"rollbackId": selected_rollback_id},
    )
    click.echo("rollback_triggered=true")
    if not wait:
        return
    result = _wait_for_dokploy_deployment(
        host=host,
        token=token,
        application_id=application_id,
        before_key=before_key,
        timeout_seconds=timeout_seconds,
    )
    click.echo(result)


@main.command("init")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
def init(stack_file: Path, context_name: str, instance_name: str) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(repo_root, None)
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    install_modules = ",".join(runtime_selection.effective_install_modules)
    command = [
        "/odoo/odoo-bin",
        "-c",
        runtime_selection.runtime_odoo_conf_path,
        "-d",
        runtime_selection.database_name,
        "-i",
        install_modules,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    _compose_exec(runtime_env_file, "script-runner", command)
    click.echo(f"init={runtime_selection.project_name}")


@main.command("update")
@click.option(
    "--stack-file",
    type=click.Path(path_type=Path),
    default=Path("platform/stack.toml"),
    show_default=True,
)
@click.option("--context", "context_name", required=True)
@click.option("--instance", "instance_name", default="local", show_default=True)
def update(stack_file: Path, context_name: str, instance_name: str) -> None:
    repo_root = _discover_repo_root(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = _load_stack(stack_file_path)
    runtime_selection = _resolve_runtime_selection(loaded_stack.stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = _load_environment(repo_root, None)
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )

    update_modules = runtime_selection.context_definition.update_modules
    module_argument = ",".join(runtime_selection.effective_install_modules)
    if update_modules.upper() != "AUTO":
        module_argument = update_modules

    command = [
        "/odoo/odoo-bin",
        "-c",
        runtime_selection.runtime_odoo_conf_path,
        "-d",
        runtime_selection.database_name,
        "-u",
        module_argument,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    _compose_exec(runtime_env_file, "script-runner", command)
    click.echo(f"update={runtime_selection.project_name}")


if __name__ == "__main__":
    main()
