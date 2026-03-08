from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import click

from .dokploy import as_json_object
from .models import JsonObject, JsonValue


def parse_compose_ps_output(raw_output: str) -> list[JsonObject]:
    stripped_output = raw_output.strip()
    if not stripped_output:
        return []

    try:
        parsed_payload = json.loads(stripped_output)
    except ValueError:
        parsed_payload = None

    parsed_objects: list[JsonObject] = []
    if isinstance(parsed_payload, list):
        for item in parsed_payload:
            parsed_item = as_json_object(cast(JsonValue, item))
            if parsed_item is not None:
                parsed_objects.append(parsed_item)
        return parsed_objects
    if isinstance(parsed_payload, dict):
        parsed_item = as_json_object(parsed_payload)
        if parsed_item is not None:
            parsed_objects.append(parsed_item)
        return parsed_objects

    for raw_line in stripped_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            line_payload = json.loads(line)
        except ValueError:
            continue
        parsed_item = as_json_object(cast(JsonValue, line_payload))
        if parsed_item is not None:
            parsed_objects.append(parsed_item)
    return parsed_objects


def _as_int(value: JsonValue) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _normalize_compose_service_status(service_payload: JsonObject) -> JsonObject:
    published_ports: list[JsonValue] = []
    publishers_payload = service_payload.get("Publishers")
    if isinstance(publishers_payload, list):
        for publisher in publishers_payload:
            publisher_payload = as_json_object(cast(JsonValue, publisher))
            if publisher_payload is None:
                continue
            published_ports.append(
                {
                    "url": str(publisher_payload.get("URL") or ""),
                    "protocol": str(publisher_payload.get("Protocol") or ""),
                    "target_port": _as_int(publisher_payload.get("TargetPort")),
                    "published_port": _as_int(publisher_payload.get("PublishedPort")),
                }
            )

    return {
        "name": str(service_payload.get("Name") or ""),
        "service": str(service_payload.get("Service") or ""),
        "state": str(service_payload.get("State") or "").lower(),
        "status": str(service_payload.get("Status") or ""),
        "health": str(service_payload.get("Health") or ""),
        "exit_code": _as_int(service_payload.get("ExitCode")),
        "published_ports": published_ports,
    }


def local_runtime_status(
    runtime_env_file: Path,
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_capture_fn: Callable[[list[str]], str],
) -> JsonObject:
    status_payload: JsonObject = {
        "runtime_env_file": str(runtime_env_file),
        "runtime_env_exists": runtime_env_file.exists(),
        "project_running": False,
        "running_services": 0,
        "services": [],
    }
    if not runtime_env_file.exists():
        status_payload["state"] = "not_selected"
        return status_payload

    compose_command = compose_base_command_fn(runtime_env_file)
    try:
        raw_output = run_command_capture_fn(compose_command + ["ps", "--format", "json"])
    except click.ClickException as error:
        status_payload["state"] = "error"
        status_payload["compose_error"] = error.message
        return status_payload

    services = [_normalize_compose_service_status(item) for item in parse_compose_ps_output(raw_output)]
    running_services = [
        service_payload
        for service_payload in services
        if str(service_payload.get("state") or "").lower() == "running"
    ]
    status_payload["state"] = "running" if running_services else "stopped"
    status_payload["project_running"] = bool(running_services)
    status_payload["running_services"] = len(running_services)
    serialized_services: list[JsonValue] = []
    for service_payload in services:
        serialized_services.append(service_payload)
    status_payload["services"] = serialized_services
    return status_payload
