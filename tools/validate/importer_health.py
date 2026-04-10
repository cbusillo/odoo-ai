import json
import xmlrpc.client
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from tools.platform import dokploy as platform_dokploy
from tools.platform import environment as platform_environment
from tools.platform import runtime as platform_runtime

DEFAULT_REMOTE_LOGIN = "gpt-admin"
SUPPORTED_INSTANCES = ("local", "dev", "testing", "prod")
SUPPORTED_IMPORTERS = ("cm-data", "fishbowl", "repairshopr")


@dataclass(frozen=True)
class RemoteOdooSettings:
    odoo_url: str
    database_name: str
    odoo_password: str
    remote_login: str


class RemoteOdooClient:
    def __init__(self, settings: RemoteOdooSettings) -> None:
        common_proxy = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common_proxy.authenticate(settings.database_name, settings.remote_login, settings.odoo_password, {})
        if not uid:
            raise RuntimeError(f"Failed to authenticate remote Odoo XML-RPC session for {settings.remote_login}")
        self.settings = settings
        self.uid = uid
        self.object_proxy = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/object", allow_none=True)

    def execute(self, model_name: str, method_name: str, args: list[object], kwargs: dict[str, object] | None = None) -> object:
        return self.object_proxy.execute_kw(
            self.settings.database_name,
            self.uid,
            self.settings.odoo_password,
            model_name,
            method_name,
            args,
            kwargs or {},
        )


def load_settings(
    *,
    repository_root: Path,
    env_file: Path | None,
    context_name: str,
    instance_name: str,
    remote_login: str,
) -> RemoteOdooSettings:
    if instance_name not in SUPPORTED_INSTANCES:
        raise click.ClickException(f"importer-health currently supports these instances: {', '.join(SUPPORTED_INSTANCES)}")
    _, environment_values = platform_environment.load_environment(
        repository_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode="error",
    )
    odoo_url = _resolve_odoo_url(
        repository_root=repository_root,
        environment_values=environment_values,
        context_name=context_name,
        instance_name=instance_name,
    )
    database_name = str(environment_values.get("ODOO_DB_NAME", context_name)).strip() or context_name
    odoo_password = str(environment_values["ODOO_KEY"]).strip()
    if not odoo_password:
        raise click.ClickException(f"Missing ODOO_KEY for {context_name}/{instance_name} importer health validation.")
    return RemoteOdooSettings(
        odoo_url=odoo_url,
        database_name=database_name,
        odoo_password=odoo_password,
        remote_login=remote_login,
    )


def _resolve_odoo_url(
    *,
    repository_root: Path,
    environment_values: dict[str, str],
    context_name: str,
    instance_name: str,
) -> str:
    configured_base_url = str(environment_values.get("ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL", "")).strip()
    if configured_base_url:
        return configured_base_url.rstrip("/")
    if instance_name == "local":
        loaded_stack = platform_environment.load_stack(repository_root / "platform" / "stack.toml")
        runtime_selection = platform_runtime.resolve_runtime_selection(
            loaded_stack.stack_definition,
            context_name,
            instance_name,
            platform_environment.discover_repo_root,
        )
        return f"http://127.0.0.1:{runtime_selection.web_host_port}"
    dokploy_source_file = repository_root / "platform" / "dokploy.toml"
    dokploy_source_of_truth = platform_environment.load_dokploy_source_of_truth(dokploy_source_file)
    target_definition = platform_dokploy.find_dokploy_target_definition(
        dokploy_source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    base_urls = platform_dokploy.resolve_healthcheck_base_urls(
        target_definition=target_definition,
        environment_values=environment_values,
    )
    if base_urls:
        return str(base_urls[0]).rstrip("/")
    raise click.ClickException(
        f"Could not resolve base URL for {context_name}/{instance_name}. Configure ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL or Dokploy domains."
    )


def _search_count(client: RemoteOdooClient, model_name: str, domain: list[list[object]]) -> int:
    result = client.execute(model_name, "search_count", [domain])
    if not isinstance(result, int):
        raise RuntimeError(f"Unexpected search_count payload for {model_name}: {result!r}")
    return result


def _read_config_parameters(client: RemoteOdooClient, keys: tuple[str, ...]) -> dict[str, str]:
    parameter_rows = client.execute(
        "ir.config_parameter",
        "search_read",
        [[["key", "in", list(keys)]]],
        {"fields": ["key", "value"], "context": {"active_test": False}},
    )
    if not isinstance(parameter_rows, list):
        raise RuntimeError(f"Unexpected ir.config_parameter payload: {parameter_rows!r}")
    values_by_key = {key: "" for key in keys}
    for row in parameter_rows:
        if not isinstance(row, dict):
            continue
        key = row.get("key")
        value = row.get("value")
        if isinstance(key, str):
            values_by_key[key] = "" if value in (None, False) else str(value)
    return values_by_key


def _build_generic_importer_snapshot(
    *,
    importer_name: str,
    system_code: str,
    last_run_prefix: str,
    resume_state_key: str | None,
    external_id_resources: tuple[str, ...],
    client: RemoteOdooClient,
) -> dict[str, object]:
    parameter_keys = (
        f"{last_run_prefix}.last_run_status",
        f"{last_run_prefix}.last_run_message",
        f"{last_run_prefix}.last_run_at",
        f"{last_run_prefix}.last_sync_at",
        *((resume_state_key,) if resume_state_key is not None else ()),
    )
    parameter_values = _read_config_parameters(client, parameter_keys)
    external_id_counts = {
        resource_name: _search_count(
            client,
            "external.id",
            [
                ["system_id.code", "=", system_code],
                ["resource", "=", resource_name],
            ],
        )
        for resource_name in external_id_resources
    }
    raw_resume_state = parameter_values.get(resume_state_key, "") if resume_state_key else ""
    parsed_resume_state: dict[str, Any] | None = None
    if raw_resume_state:
        try:
            loaded_resume_state = json.loads(raw_resume_state)
        except json.JSONDecodeError:
            loaded_resume_state = {"raw": raw_resume_state, "parse_error": True}
        if isinstance(loaded_resume_state, dict):
            parsed_resume_state = loaded_resume_state
        else:
            parsed_resume_state = {"raw": loaded_resume_state}
    checks = {
        "last_run_success": parameter_values[f"{last_run_prefix}.last_run_status"] == "success",
        "resume_state_clean": not raw_resume_state if resume_state_key else True,
    }
    return {
        "importer": importer_name,
        "ok": all(checks.values()),
        "checks": checks,
        "last_run": {
            "status": parameter_values[f"{last_run_prefix}.last_run_status"],
            "message": parameter_values[f"{last_run_prefix}.last_run_message"],
            "at": parameter_values[f"{last_run_prefix}.last_run_at"],
            "last_sync_at": parameter_values[f"{last_run_prefix}.last_sync_at"],
        },
        "resume_state": {
            "raw": raw_resume_state,
            "parsed": parsed_resume_state,
        }
        if resume_state_key
        else None,
        "metrics": {
            "external_id_counts": external_id_counts,
        },
    }


def collect_importer_snapshot(client: RemoteOdooClient, importer_name: str) -> dict[str, object]:
    if importer_name == "cm-data":
        result = client.execute("integration.cm_data.importer", "get_validation_health_snapshot", [])
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected CM importer health payload: {result!r}")
        return result
    if importer_name == "fishbowl":
        return _build_generic_importer_snapshot(
            importer_name="fishbowl",
            system_code="fishbowl",
            last_run_prefix="fishbowl",
            resume_state_key="fishbowl.resume_state",
            external_id_resources=(
                "customer",
                "vendor",
                "part",
                "product",
                "uom",
                "so",
                "soitem",
                "po",
                "poitem",
                "ship",
                "shipitem",
                "receipt",
                "receiptitem",
            ),
            client=client,
        )
    if importer_name == "repairshopr":
        return _build_generic_importer_snapshot(
            importer_name="repairshopr",
            system_code="repairshopr",
            last_run_prefix="repairshopr",
            resume_state_key="repairshopr.resume_state",
            external_id_resources=("customer", "contact", "product", "ticket", "estimate", "invoice"),
            client=client,
        )
    raise ValueError(f"Unsupported importer '{importer_name}'")


def run_validation_command(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    importers: tuple[str, ...],
    repository_root: Path,
) -> dict[str, object]:
    requested_importers = importers or SUPPORTED_IMPORTERS
    settings = load_settings(
        repository_root=repository_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        remote_login=remote_login,
    )
    client = RemoteOdooClient(settings)
    importer_results: dict[str, dict[str, object]] = {}
    failed_importers: list[str] = []
    for importer_name in requested_importers:
        try:
            snapshot = collect_importer_snapshot(client, importer_name)
        except Exception as exc:
            snapshot = {
                "importer": importer_name,
                "ok": False,
                "error": str(exc),
            }
        importer_results[importer_name] = snapshot
        if not bool(snapshot.get("ok")):
            failed_importers.append(importer_name)
    return {
        "scenario": "importer-health",
        "context": context_name,
        "instance": instance_name,
        "remote_odoo_url": settings.odoo_url,
        "requested_importers": list(requested_importers),
        "overall_ok": not failed_importers,
        "failed_importers": failed_importers,
        "importers": importer_results,
    }
