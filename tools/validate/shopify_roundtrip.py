from __future__ import annotations

import html
import json
import sys
import time
import urllib.request
import xmlrpc.client
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from tools.platform import dokploy as platform_dokploy
from tools.platform.environment import discover_repo_root, load_dokploy_source_of_truth, load_environment

POLL_SECONDS = 5
SYNC_TIMEOUT_SECONDS = 8 * 60 * 60
TITLE_TIMEOUT_SECONDS = 180
FIELD_TIMEOUT_SECONDS = 180
SYNC_SEARCH_CUTOFF_SECONDS = 300
SYNC_SETTLE_TIMEOUT_SECONDS = 300
SYNC_SETTLE_QUIET_SECONDS = 15
DEFAULT_REMOTE_LOGIN = "gpt-admin"
SUPPORTED_REMOTE_INSTANCES = ("dev", "testing", "prod")
VALIDATION_PROFILES = ("smoke", "full")
DEFAULT_SAMPLE_SIZE = 25
VALIDATION_EXPORT_MARKER_OFFSET_SECONDS = 60 * 60
SHOPIFY_DISPATCHER_CRON_NAME = "Shopify Sync – Dispatcher"
SHOPIFY_WEBHOOK_PAUSE_KEY = "shopify.pause_webhook_processing"
SHOPIFY_AUTOSCHEDULE_PAUSE_KEY = "shopify.pause_sync_autoschedule"
PREPARE_SYNC_MODES = ("reset_shopify", "export_all_products", "import_then_export_products", "export_changed_products", "export_batch_products")
ROUNDTRIP_SYNC_MODES = ("import_then_export_products", "export_changed_products", "import_one_product", "export_batch_products")
SHOPIFY_METAFIELD_NAMESPACE = "custom"
CONDITION_METAFIELD_KEY = "condition"
CONFLICTING_SYNC_STATES = ("queued", "running")


@dataclass(frozen=True)
class RemoteShopifySettings:
    odoo_url: str
    database_name: str
    odoo_password: str
    remote_login: str
    shop_url_key: str
    shopify_api_token: str
    shopify_api_version: str


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: int
    title: str
    description_html: str
    condition_id: int | None
    condition_code: str | None


@dataclass(frozen=True)
class ShopifyProductSnapshot:
    title: str | None
    description_html: str | None
    condition_metafield_id: str | None
    condition_code: str | None


@dataclass(frozen=True)
class RoundtripProductSelection:
    product_snapshot: ProductSnapshot
    shopify_product_id: str
    export_product_ids: tuple[int, ...]


def read_config_parameter(client: RemoteOdooClient, key: str) -> dict[str, object] | None:
    result = client.execute(
        "ir.config_parameter",
        "search_read",
        [[["key", "=", key]]],
        {"fields": ["id", "key", "value"], "limit": 1, "context": {"active_test": False}},
    )
    if not isinstance(result, list) or not result:
        return None
    return result[0] if isinstance(result[0], dict) else None


def set_config_parameter(client: RemoteOdooClient, key: str, value: str | None) -> dict[str, object] | None:
    existing_row = read_config_parameter(client, key)
    if existing_row and isinstance(existing_row.get("id"), int):
        if value is None:
            client.execute("ir.config_parameter", "unlink", [[existing_row["id"]]])
            return None
        client.execute("ir.config_parameter", "write", [[existing_row["id"]], {"value": value}])
        return read_config_parameter(client, key)
    if value is None:
        return None
    client.execute("ir.config_parameter", "create", [[{"key": key, "value": value}]])
    return read_config_parameter(client, key)


def pause_webhook_processing(client: RemoteOdooClient) -> str | None:
    existing_row = read_config_parameter(client, SHOPIFY_WEBHOOK_PAUSE_KEY)
    original_value = str(existing_row.get("value")) if existing_row and existing_row.get("value") is not None else None
    updated_row = set_config_parameter(client, SHOPIFY_WEBHOOK_PAUSE_KEY, "1")
    print(
        json.dumps(
            {"label": "pause webhook processing", "config_parameter": updated_row or {"key": SHOPIFY_WEBHOOK_PAUSE_KEY, "value": None}},
            sort_keys=True,
        ),
        flush=True,
    )
    return original_value


def restore_webhook_processing(client: RemoteOdooClient, *, original_value: str | None) -> None:
    restored_row = set_config_parameter(client, SHOPIFY_WEBHOOK_PAUSE_KEY, original_value)
    print(
        json.dumps(
            {"label": "restore webhook processing", "config_parameter": restored_row or {"key": SHOPIFY_WEBHOOK_PAUSE_KEY, "value": None}},
            sort_keys=True,
        ),
        flush=True,
    )


def pause_sync_autoschedule(client: RemoteOdooClient) -> str | None:
    existing_row = read_config_parameter(client, SHOPIFY_AUTOSCHEDULE_PAUSE_KEY)
    original_value = str(existing_row.get("value")) if existing_row and existing_row.get("value") is not None else None
    updated_row = set_config_parameter(client, SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "1")
    print(
        json.dumps(
            {"label": "pause Shopify autoschedule", "config_parameter": updated_row or {"key": SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": None}},
            sort_keys=True,
        ),
        flush=True,
    )
    return original_value


def restore_sync_autoschedule(client: RemoteOdooClient, *, original_value: str | None) -> None:
    restored_row = set_config_parameter(client, SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, original_value)
    print(
        json.dumps(
            {"label": "restore Shopify autoschedule", "config_parameter": restored_row or {"key": SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": None}},
            sort_keys=True,
        ),
        flush=True,
    )


def read_dispatcher_cron(client: RemoteOdooClient) -> dict[str, object]:
    result = client.execute(
        "ir.cron",
        "search_read",
        [[["cron_name", "=", SHOPIFY_DISPATCHER_CRON_NAME]]],
        {"fields": ["id", "active", "nextcall", "lastcall", "failure_count"], "limit": 1, "context": {"active_test": False}},
    )
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise RuntimeError(f"Could not find {SHOPIFY_DISPATCHER_CRON_NAME!r} on remote Odoo")
    return result[0]


def set_dispatcher_cron_active(client: RemoteOdooClient, *, active: bool, label: str) -> dict[str, object]:
    cron_row = read_dispatcher_cron(client)
    cron_id = cron_row.get("id")
    if not isinstance(cron_id, int):
        raise RuntimeError(f"Unexpected dispatcher cron payload: {cron_row!r}")
    if bool(cron_row.get("active")) != active:
        client.execute("ir.cron", "write", [[cron_id], {"active": active}])
        cron_row = read_dispatcher_cron(client)
    print(json.dumps({"label": label, "dispatcher_cron": cron_row}, sort_keys=True), flush=True)
    return cron_row


def pause_dispatcher_cron(client: RemoteOdooClient) -> bool:
    cron_row = read_dispatcher_cron(client)
    was_active = bool(cron_row.get("active"))
    set_dispatcher_cron_active(client, active=False, label="pause dispatcher cron")
    return was_active


def restore_dispatcher_cron(client: RemoteOdooClient, *, originally_active: bool) -> None:
    set_dispatcher_cron_active(client, active=originally_active, label="restore dispatcher cron")


def list_conflicting_syncs(client: RemoteOdooClient) -> list[dict[str, object]]:
    result = client.execute(
        "shopify.sync",
        "search_read",
        [[["state", "in", list(CONFLICTING_SYNC_STATES)]]],
        {
            "fields": ["id", "mode", "state", "create_date", "write_date", "error_message"],
            "order": "id asc",
            "limit": 50,
        },
    )
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected payload while listing conflicting Shopify syncs: {result!r}")
    return [row for row in result if isinstance(row, dict)]


def read_validation_runtime_state(client: RemoteOdooClient) -> dict[str, object]:
    return {
        "dispatcher_cron": read_dispatcher_cron(client),
        "autoschedule_pause": read_config_parameter(client, SHOPIFY_AUTOSCHEDULE_PAUSE_KEY),
        "webhook_pause": read_config_parameter(client, SHOPIFY_WEBHOOK_PAUSE_KEY),
        "active_syncs": list_conflicting_syncs(client),
    }


def _build_operator_summary(
    *,
    context_name: str,
    instance_name: str,
    results: dict[str, object],
    runtime_state: dict[str, object],
    sample_size: int,
) -> dict[str, object]:
    checks_completed = [
        "prepare reset/export",
        "odoo_to_shopify title/description/metafield",
        "shopify_to_odoo title/description/metafield",
        "restore original product state",
    ]
    profile = str(results.get("profile") or "")
    export_sample_product_ids = results.get("export_sample_product_ids")
    active_syncs = runtime_state.get("active_syncs")
    active_sync_count = len(active_syncs) if isinstance(active_syncs, list) else None
    export_sample_count = len(export_sample_product_ids) if isinstance(export_sample_product_ids, list) else (sample_size if profile == "smoke" else None)
    return {
        "scenario": "shopify-roundtrip",
        "context": context_name,
        "instance": instance_name,
        "profile": profile,
        "start_mode": results.get("start_mode"),
        "candidate_product_id": results.get("candidate_product_id"),
        "shopify_product_id": results.get("shopify_product_id"),
        "export_sample_count": export_sample_count,
        "prepare_sync_mode": results.get("prepare_sync_mode"),
        "checks_completed": checks_completed,
        "post_validation_active_sync_count": active_sync_count,
    }


def _export_candidate_domain() -> list[list[object]]:
    return [
        ["sale_ok", "=", True],
        ["is_ready_for_sale", "=", True],
        ["is_published", "=", True],
        ["website_description", "!=", False],
        ["website_description", "!=", ""],
        ["type", "=", "consu"],
        ["external_ids.system_id.code", "=", "shopify"],
        ["external_ids.resource", "=", "product"],
    ]


def clear_conflicting_syncs(client: RemoteOdooClient, *, reason: str) -> list[int]:
    conflicting_syncs = list_conflicting_syncs(client)
    conflicting_sync_ids: list[int] = []
    queued_sync_ids: list[int] = []
    running_sync_ids: list[int] = []
    for row in conflicting_syncs:
        sync_id = row.get("id")
        if isinstance(sync_id, int):
            conflicting_sync_ids.append(sync_id)
            state_value = str(row.get("state") or "")
            if state_value == "queued":
                queued_sync_ids.append(sync_id)
            elif state_value == "running":
                running_sync_ids.append(sync_id)

    if queued_sync_ids:
        client.execute(
            "shopify.sync",
            "write",
            [queued_sync_ids, {"state": "canceled", "error_message": reason}],
        )
    if running_sync_ids:
        client.execute(
            "shopify.sync",
            "write",
            [running_sync_ids, {"cancel_requested": True, "cancel_reason": reason}],
        )
    return conflicting_sync_ids


def ensure_no_conflicting_syncs(client: RemoteOdooClient, *, clear_conflicts: bool) -> None:
    conflicting_syncs = list_conflicting_syncs(client)
    if not conflicting_syncs:
        return
    if clear_conflicts:
        cleared_sync_ids = clear_conflicting_syncs(
            client,
            reason="Canceled before Shopify round-trip validation via --clear-conflicting-syncs",
        )
        print(
            json.dumps(
                {
                    "label": "clear conflicting syncs",
                    "cleared_sync_ids": cleared_sync_ids,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return
    raise click.ClickException(
        "Conflicting Shopify syncs already exist. Re-run with --clear-conflicting-syncs if you want the validator to cancel them first. "
        f"Current conflicts: {json.dumps(conflicting_syncs, sort_keys=True)}"
    )


def load_settings(
    *,
    repository_root: Path,
    env_file: Path | None,
    context_name: str,
    instance_name: str,
    remote_login: str,
) -> RemoteShopifySettings:
    if instance_name not in SUPPORTED_REMOTE_INSTANCES:
        raise click.ClickException(
            f"shopify-roundtrip currently supports remote instances only: {', '.join(SUPPORTED_REMOTE_INSTANCES)}"
        )

    _, environment_values = load_environment(
        repository_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
        collision_mode="error",
    )
    dokploy_source_file = repository_root / "platform" / "dokploy.toml"
    dokploy_source_of_truth = load_dokploy_source_of_truth(dokploy_source_file)
    target_definition = platform_dokploy.find_dokploy_target_definition(
        dokploy_source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    base_urls = platform_dokploy.resolve_healthcheck_base_urls(
        target_definition=target_definition,
        environment_values=environment_values,
    )
    if not base_urls:
        raise click.ClickException(
            f"Could not resolve base URL for {context_name}/{instance_name}. Configure platform/dokploy.toml domains or ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL."
        )
    odoo_url = base_urls[0]
    odoo_key = str(environment_values["ODOO_KEY"])
    database_name = str(environment_values.get("ODOO_DB_NAME", context_name)).strip()
    if not database_name:
        database_name = context_name
    return RemoteShopifySettings(
        odoo_url=odoo_url,
        database_name=database_name,
        odoo_password=odoo_key,
        remote_login=remote_login,
        shop_url_key=str(environment_values["ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY"]),
        shopify_api_token=str(environment_values["ENV_OVERRIDE_SHOPIFY__API_TOKEN"]),
        shopify_api_version=str(environment_values["ENV_OVERRIDE_SHOPIFY__API_VERSION"]),
    )


class RemoteOdooClient:
    def __init__(self, settings: RemoteShopifySettings) -> None:
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


def shopify_graphql(settings: RemoteShopifySettings, query: str, variables: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url=f"https://{settings.shop_url_key}.myshopify.com/admin/api/{settings.shopify_api_version}/graphql.json",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": settings.shopify_api_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Shopify GraphQL errors: {payload['errors']}")
    return payload.get("data") or {}


def shopify_product_gid(shopify_product_id: str) -> str:
    return f"gid://shopify/Product/{shopify_product_id}"


def get_shopify_title(settings: RemoteShopifySettings, shopify_product_id: str) -> str | None:
    return get_shopify_product_snapshot(settings, shopify_product_id).title


def get_shopify_product_snapshot(settings: RemoteShopifySettings, shopify_product_id: str) -> ShopifyProductSnapshot:
    data = shopify_graphql(
        settings,
        query=(
            "query ProductSnapshot($id: ID!) {"
            "  product(id: $id) {"
            "    title"
            "    descriptionHtml"
            "    metafields(first: 15, namespace: \"custom\") {"
            "      nodes { id key value }"
            "    }"
            "  }"
            "}"
        ),
        variables={"id": shopify_product_gid(shopify_product_id)},
    )
    product_payload = data.get("product") or {}
    if not isinstance(product_payload, dict):
        raise RuntimeError("Unexpected Shopify product payload while reading product snapshot")

    condition_metafield_id = None
    condition_code = None
    metafields_payload = product_payload.get("metafields") or {}
    metafield_nodes = metafields_payload.get("nodes") if isinstance(metafields_payload, dict) else []
    if isinstance(metafield_nodes, list):
        for metafield in metafield_nodes:
            if not isinstance(metafield, dict):
                continue
            if metafield.get("key") != CONDITION_METAFIELD_KEY:
                continue
            metafield_id = metafield.get("id")
            metafield_value = metafield.get("value")
            condition_metafield_id = str(metafield_id) if metafield_id else None
            condition_code = str(metafield_value) if metafield_value is not None else None
            break

    return ShopifyProductSnapshot(
        title=str(product_payload.get("title")) if product_payload.get("title") is not None else None,
        description_html=(
            str(product_payload.get("descriptionHtml")) if product_payload.get("descriptionHtml") is not None else None
        ),
        condition_metafield_id=condition_metafield_id,
        condition_code=condition_code,
    )


def set_shopify_title(settings: RemoteShopifySettings, shopify_product_id: str, title: str) -> None:
    update_shopify_product_snapshot(settings, shopify_product_id, title=title)


def update_shopify_product_snapshot(
    settings: RemoteShopifySettings,
    shopify_product_id: str,
    *,
    title: str | None = None,
    description_html: str | None = None,
    condition_code: str | None = None,
    condition_metafield_id: str | None = None,
) -> None:
    input_payload: dict[str, object] = {}
    if title is not None:
        input_payload["title"] = title
    if description_html is not None:
        input_payload["descriptionHtml"] = description_html
    if condition_code is not None:
        metafield_payload: dict[str, object] = {
            "namespace": SHOPIFY_METAFIELD_NAMESPACE,
            "key": CONDITION_METAFIELD_KEY,
            "value": condition_code,
            "type": "single_line_text_field",
        }
        if condition_metafield_id:
            metafield_payload["id"] = condition_metafield_id
        input_payload["metafields"] = [metafield_payload]

    if not input_payload:
        return

    data = shopify_graphql(
        settings,
        query=(
            "mutation ProductSet($identifier: ProductSetIdentifiers!, $input: ProductSetInput!) {"
            "  productSet(identifier: $identifier, input: $input) {"
            "    product { id title }"
            "    userErrors { field message }"
            "  }"
            "}"
        ),
        variables={
            "identifier": {"id": shopify_product_gid(shopify_product_id)},
            "input": input_payload,
        },
    )
    response_payload = data.get("productSet") or {}
    if not isinstance(response_payload, dict):
        raise RuntimeError("Unexpected Shopify productSet payload while updating title")
    user_errors = response_payload.get("userErrors") or []
    if user_errors:
        raise RuntimeError(f"Shopify title update failed: {user_errors}")


def search_export_candidate(client: RemoteOdooClient) -> dict[str, object]:
    domain = [
        ["sale_ok", "=", True],
        ["is_ready_for_sale", "=", True],
        ["is_published", "=", True],
        ["website_description", "!=", False],
        ["website_description", "!=", ""],
        ["type", "=", "consu"],
        ["external_ids.system_id.code", "=", "shopify"],
        ["external_ids.resource", "=", "product"],
    ]
    result = client.execute(
        "product.product",
        "search_read",
        [domain],
        {"fields": ["id", "name"], "limit": 1},
    )
    if not isinstance(result, list) or not result:
        raise RuntimeError("No Shopify-linked product found for Shopify round-trip validation")
    candidate = result[0]
    if not isinstance(candidate, dict):
        raise RuntimeError("Unexpected search_read payload for candidate product")
    return candidate


def search_export_candidates(client: RemoteOdooClient) -> list[dict[str, object]]:
    domain = _export_candidate_domain()
    result = client.execute(
        "product.product",
        "search_read",
        [domain],
        {"fields": ["id", "name"], "order": "id asc"},
    )
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected search_read payload for Shopify export candidates: {result!r}")
    return [row for row in result if isinstance(row, dict)]


def _sample_product_ids(product_ids: list[int], *, sample_size: int) -> tuple[int, ...]:
    if sample_size <= 0:
        raise RuntimeError(f"Smoke profile sample size must be positive, got {sample_size}")
    if not product_ids:
        raise RuntimeError("No Shopify-linked products available for smoke validation")
    if len(product_ids) <= sample_size:
        return tuple(product_ids)

    last_index = len(product_ids) - 1
    if sample_size == 1:
        return (product_ids[last_index // 2],)

    sampled_ids: list[int] = []
    seen_product_ids: set[int] = set()
    for position in range(sample_size):
        candidate_index = round(position * last_index / (sample_size - 1))
        candidate_product_id = product_ids[candidate_index]
        if candidate_product_id in seen_product_ids:
            continue
        sampled_ids.append(candidate_product_id)
        seen_product_ids.add(candidate_product_id)

    if len(sampled_ids) < sample_size:
        for candidate_product_id in product_ids:
            if candidate_product_id in seen_product_ids:
                continue
            sampled_ids.append(candidate_product_id)
            seen_product_ids.add(candidate_product_id)
            if len(sampled_ids) == sample_size:
                break

    return tuple(sampled_ids)


def _inject_primary_product_id(sampled_product_ids: tuple[int, ...], *, primary_product_id: int, sample_size: int) -> tuple[int, ...]:
    if primary_product_id in sampled_product_ids:
        return sampled_product_ids
    adjusted_product_ids = (primary_product_id, *tuple(pid for pid in sampled_product_ids if pid != primary_product_id))
    return adjusted_product_ids[:sample_size]


def get_external_system_id(client: RemoteOdooClient, product_id: int, resource: str) -> str:
    external_id = client.execute("product.product", "get_external_system_id", [[product_id], "shopify", resource])
    if not isinstance(external_id, str) or not external_id:
        raise RuntimeError(f"Product {product_id} is missing Shopify {resource} external id")
    return external_id


def read_product_name(client: RemoteOdooClient, product_id: int) -> str:
    result = client.execute("product.product", "read", [[product_id], ["name"]])
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise RuntimeError(f"Failed to read product {product_id}")
    return str(result[0].get("name") or "")


def read_product_snapshot(client: RemoteOdooClient, product_id: int) -> ProductSnapshot:
    result = client.execute(
        "product.product",
        "read",
        [[product_id], ["name", "website_description", "condition"]],
    )
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise RuntimeError(f"Failed to read product snapshot for product {product_id}")

    product_payload = result[0]
    condition_value = product_payload.get("condition")
    condition_id = None
    condition_code = None
    if isinstance(condition_value, list) and condition_value and isinstance(condition_value[0], int):
        condition_id = condition_value[0]
        condition_rows = client.execute("product.condition", "read", [[condition_id], ["code"]])
        if isinstance(condition_rows, list) and condition_rows and isinstance(condition_rows[0], dict):
            code_value = condition_rows[0].get("code")
            condition_code = str(code_value) if code_value else None

    return ProductSnapshot(
        product_id=product_id,
        title=str(product_payload.get("name") or ""),
        description_html=str(product_payload.get("website_description") or ""),
        condition_id=condition_id,
        condition_code=condition_code,
    )


def stamp_non_sample_products_as_exported_for_validation(
    client: RemoteOdooClient,
    *,
    keep_product_ids: tuple[int, ...],
) -> str:
    stamp_timestamp = _future_utc_timestamp(VALIDATION_EXPORT_MARKER_OFFSET_SECONDS)
    domain = _export_candidate_domain()
    if keep_product_ids:
        domain.append(["id", "not in", list(keep_product_ids)])
    product_ids_to_stamp = client.execute("product.product", "search", [domain])
    if not isinstance(product_ids_to_stamp, list):
        raise RuntimeError(f"Unexpected product search payload while stamping validation export state: {product_ids_to_stamp!r}")
    if product_ids_to_stamp:
        client.execute(
            "product.product",
            "write",
            [product_ids_to_stamp, {"shopify_last_exported_at": stamp_timestamp, "shopify_next_export": False}],
        )
    print(
        json.dumps(
            {
                "label": "stamp validation export state",
                "product_count": len(product_ids_to_stamp),
                "kept_product_count": len(keep_product_ids),
                "shopify_last_exported_at": stamp_timestamp,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return stamp_timestamp


def select_alternate_condition(client: RemoteOdooClient, *, exclude_condition_id: int | None) -> tuple[int, str] | None:
    domain: list[list[object]] = [
        ["code", "!=", False],
    ]
    if exclude_condition_id is not None:
        domain.append(["id", "!=", exclude_condition_id])

    result = client.execute(
        "product.condition",
        "search_read",
        [domain],
        {"fields": ["id", "code"], "limit": 1, "order": "id asc"},
    )
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return None

    condition_id = result[0].get("id")
    condition_code = result[0].get("code")
    if not isinstance(condition_id, int) or not condition_code:
        return None
    return condition_id, str(condition_code)


def _correlate_sync_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _fallback_sync_window_start() -> str:
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() - SYNC_SEARCH_CUTOFF_SECONDS),
    )


def _current_utc_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _future_utc_timestamp(offset_seconds: int) -> str:
    return (datetime.now(tz=UTC) + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_html_fragment(value: str | None) -> str:
    return html.unescape(value or "")


def _parse_odoo_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def create_sync(client: RemoteOdooClient, mode: str, extra_values: dict[str, object] | None = None) -> int:
    values: dict[str, object] = {"mode": mode}
    if extra_values:
        values.update(extra_values)

    timestamped_values = dict(values)
    sync_timestamp = None
    if "datetime_to_sync" not in timestamped_values:
        sync_timestamp = _correlate_sync_timestamp()
        timestamped_values["datetime_to_sync"] = sync_timestamp

    sync_record = client.execute("shopify.sync", "create_and_run_async", [[], timestamped_values])
    sync_id: int | None = None
    if isinstance(sync_record, list) and sync_record and isinstance(sync_record[0], int):
        sync_id = sync_record[0]
    elif isinstance(sync_record, int):
        sync_id = sync_record

    if sync_id is None:
        sync_candidate_domain = [
            ["mode", "=", mode],
            ["state", "in", ["queued", "running"]],
            ["user", "=", client.uid],
        ]
        if sync_timestamp is not None:
            sync_candidate_domain.append(["datetime_to_sync", "=", sync_timestamp])
        sync_candidate_domain.append(["create_date", ">=", _fallback_sync_window_start()])
        if "shopify_product_id_to_sync" in timestamped_values:
            sync_candidate_domain.append(["shopify_product_id_to_sync", "=", timestamped_values["shopify_product_id_to_sync"]])

        existing_syncs = client.execute(
            "shopify.sync",
            "search_read",
            [sync_candidate_domain],
            {"fields": ["id"], "limit": 1, "order": "id desc"},
        )
        if isinstance(existing_syncs, list) and existing_syncs and isinstance(existing_syncs[0], dict):
            existing_sync_id = existing_syncs[0].get("id")
            if isinstance(existing_sync_id, int):
                sync_id = existing_sync_id

    if sync_id is None:
        raise RuntimeError(f"Failed to create or resolve remote Shopify sync for mode {mode}: {sync_record!r}")

    client.execute("shopify.sync", "dispatch_pending_syncs_for_validation", [])
    return sync_id


def read_sync_state(client: RemoteOdooClient, sync_id: int) -> dict[str, object]:
    result = client.execute(
        "shopify.sync",
        "read",
        [[sync_id], ["id", "mode", "state", "updated_count", "total_count", "error_message"]],
    )
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise RuntimeError(f"Failed to read sync {sync_id}")
    return result[0]


def wait_for_sync(client: RemoteOdooClient, sync_id: int, label: str) -> dict[str, object]:
    deadline = time.time() + SYNC_TIMEOUT_SECONDS
    while time.time() < deadline:
        sync_state = read_sync_state(client, sync_id)
        state_value = str(sync_state.get("state") or "")
        print(json.dumps({"label": label, "sync": sync_state}, sort_keys=True), flush=True)
        if state_value == "success":
            return sync_state
        if state_value == "failed":
            raise RuntimeError(f"Remote sync failed for {label}: {sync_state}")
        if state_value == "canceled":
            raise RuntimeError(f"Remote sync was canceled for {label}: {sync_state}")
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for remote sync {sync_id} during {label}")


def assert_sync_count_at_most(sync_state: dict[str, object], *, maximum_count: int, label: str) -> None:
    total_count = sync_state.get("total_count")
    if not isinstance(total_count, int):
        raise RuntimeError(f"Unexpected sync total_count during {label}: {sync_state!r}")
    if total_count > maximum_count:
        raise RuntimeError(
            f"Unexpected sync size during {label}: expected at most {maximum_count}, got {total_count}. "
            f"Sync state: {sync_state}"
        )


def wait_for_related_syncs_to_quiet(
    client: RemoteOdooClient,
    *,
    since_timestamp: str,
    modes: tuple[str, ...],
    label: str,
) -> list[dict[str, object]]:
    deadline = time.time() + SYNC_SETTLE_TIMEOUT_SECONDS
    since_datetime = _parse_odoo_utc_timestamp(since_timestamp)
    if since_datetime is None:
        raise RuntimeError(f"Invalid settle timestamp for {label}: {since_timestamp!r}")

    while time.time() < deadline:
        result = client.execute(
            "shopify.sync",
            "search_read",
            [[["create_date", ">=", since_timestamp], ["mode", "in", list(modes)]]],
            {
                "fields": ["id", "mode", "state", "create_date", "write_date", "error_message"],
                "limit": 50,
                "order": "id asc",
            },
        )
        if not isinstance(result, list):
            raise RuntimeError(f"Unexpected sync payload while waiting for settle during {label}: {result!r}")

        sync_rows = [row for row in result if isinstance(row, dict)]
        active_rows = [row for row in sync_rows if str(row.get("state") or "") in {"queued", "running"}]

        latest_activity = since_datetime
        for row in sync_rows:
            for field_name in ("write_date", "create_date"):
                parsed_value = _parse_odoo_utc_timestamp(row.get(field_name))
                if parsed_value and parsed_value > latest_activity:
                    latest_activity = parsed_value

        quiet_seconds = (datetime.now(tz=UTC) - latest_activity).total_seconds()
        print(
            json.dumps(
                {
                    "label": label,
                    "active_sync_count": len(active_rows),
                    "recent_sync_count": len(sync_rows),
                    "quiet_seconds": round(quiet_seconds, 1),
                },
                sort_keys=True,
            ),
            flush=True,
        )

        if active_rows:
            time.sleep(POLL_SECONDS)
            continue

        if quiet_seconds < SYNC_SETTLE_QUIET_SECONDS:
            time.sleep(POLL_SECONDS)
            continue

        failed_rows = [row for row in sync_rows if str(row.get("state") or "") == "failed"]
        if failed_rows:
            raise RuntimeError(f"Related Shopify syncs failed during {label}: {failed_rows[-1]}")
        return sync_rows

    raise RuntimeError(f"Timed out waiting for related Shopify syncs to quiet during {label}")


def wait_for_shopify_title(settings: RemoteShopifySettings, shopify_product_id: str, expected_title: str, label: str) -> None:
    deadline = time.time() + TITLE_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_title = get_shopify_title(settings, shopify_product_id)
        print(json.dumps({"label": label, "expected_shopify_title": expected_title, "actual_shopify_title": actual_title}), flush=True)
        if actual_title == expected_title:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for Shopify title during {label}")


def wait_for_shopify_snapshot(
    settings: RemoteShopifySettings,
    shopify_product_id: str,
    *,
    expected_title: str | None = None,
    expected_description_html: str | None = None,
    expected_condition_code: str | None = None,
    label: str,
) -> ShopifyProductSnapshot:
    deadline = time.time() + FIELD_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_snapshot = get_shopify_product_snapshot(settings, shopify_product_id)
        print(
            json.dumps(
                {
                    "label": label,
                    "expected_shopify_title": expected_title,
                    "actual_shopify_title": actual_snapshot.title,
                    "expected_shopify_description_html": expected_description_html,
                    "actual_shopify_description_html": actual_snapshot.description_html,
                    "expected_shopify_condition_code": expected_condition_code,
                    "actual_shopify_condition_code": actual_snapshot.condition_code,
                }
            ),
            flush=True,
        )
        if expected_title is not None and actual_snapshot.title != expected_title:
            time.sleep(POLL_SECONDS)
            continue
        normalized_expected_description = _normalize_html_fragment(expected_description_html)
        normalized_actual_description = _normalize_html_fragment(actual_snapshot.description_html)
        if expected_description_html is not None and normalized_actual_description != normalized_expected_description:
            time.sleep(POLL_SECONDS)
            continue
        if expected_condition_code is not None and actual_snapshot.condition_code != expected_condition_code:
            time.sleep(POLL_SECONDS)
            continue
        return actual_snapshot
    raise RuntimeError(f"Timed out waiting for Shopify product snapshot during {label}")


def wait_for_odoo_title(client: RemoteOdooClient, product_id: int, expected_title: str, label: str) -> None:
    deadline = time.time() + TITLE_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_title = read_product_name(client, product_id)
        print(json.dumps({"label": label, "expected_odoo_title": expected_title, "actual_odoo_title": actual_title}), flush=True)
        if actual_title == expected_title:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for Odoo title during {label}")


def wait_for_odoo_snapshot(
    client: RemoteOdooClient,
    product_id: int,
    *,
    expected_title: str | None = None,
    expected_description_html: str | None = None,
    expected_condition_code: str | None = None,
    label: str,
) -> ProductSnapshot:
    deadline = time.time() + FIELD_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_snapshot = read_product_snapshot(client, product_id)
        print(
            json.dumps(
                {
                    "label": label,
                    "expected_odoo_title": expected_title,
                    "actual_odoo_title": actual_snapshot.title,
                    "expected_odoo_description_html": expected_description_html,
                    "actual_odoo_description_html": actual_snapshot.description_html,
                    "expected_odoo_condition_code": expected_condition_code,
                    "actual_odoo_condition_code": actual_snapshot.condition_code,
                }
            ),
            flush=True,
        )
        if expected_title is not None and actual_snapshot.title != expected_title:
            time.sleep(POLL_SECONDS)
            continue
        normalized_expected_description = _normalize_html_fragment(expected_description_html)
        normalized_actual_description = _normalize_html_fragment(actual_snapshot.description_html)
        if expected_description_html is not None and normalized_actual_description != normalized_expected_description:
            time.sleep(POLL_SECONDS)
            continue
        if expected_condition_code is not None and actual_snapshot.condition_code != expected_condition_code:
            time.sleep(POLL_SECONDS)
            continue
        return actual_snapshot
    raise RuntimeError(f"Timed out waiting for Odoo product snapshot during {label}")


def _run_roundtrip_for_product(
    client: RemoteOdooClient,
    settings: RemoteShopifySettings,
    *,
    product_snapshot: ProductSnapshot,
    shopify_product_id: str,
    profile: str,
) -> dict[str, object]:
    product_id = product_snapshot.product_id
    original_title = product_snapshot.title
    original_description_html = product_snapshot.description_html
    original_condition_id = product_snapshot.condition_id
    original_condition_code = product_snapshot.condition_code
    alternate_condition = select_alternate_condition(client, exclude_condition_id=original_condition_id)
    if alternate_condition is None:
        raise RuntimeError(f"No alternate Shopify-linked product.condition found for product {product_id}")
    alternate_condition_id, alternate_condition_code = alternate_condition

    odoo_to_shopify_marker = _current_utc_timestamp()
    timestamp = int(time.time())
    odoo_title = f"{original_title} [Odoo RPC {timestamp}]"
    odoo_description_html = f"<p>{original_title} Odoo description {timestamp}</p>"
    shopify_title = f"{original_title} [Shopify RPC {timestamp}]"
    shopify_description_html = f"<p>{original_title} Shopify description {timestamp}</p>"

    client.execute(
        "product.product",
        "write",
        [[product_id], {"name": odoo_title, "website_description": odoo_description_html, "condition": alternate_condition_id}],
    )
    export_changed_sync_mode = "export_changed_products"
    export_changed_sync_values: dict[str, object] | None = None
    export_changed_label = "remote export_changed_products"
    if profile == "smoke":
        export_changed_sync_mode = "export_batch_products"
        export_changed_sync_values = {"odoo_products_to_sync": [[6, 0, [product_id]]]}
        export_changed_label = "remote export_batch_products (odoo-to-shopify)"
    export_changed_sync_id = create_sync(client, export_changed_sync_mode, export_changed_sync_values)
    export_changed_sync = wait_for_sync(client, export_changed_sync_id, export_changed_label)
    if profile == "smoke":
        assert_sync_count_at_most(export_changed_sync, maximum_count=1, label=export_changed_label)
    shopify_snapshot_after_export = wait_for_shopify_snapshot(
        settings,
        shopify_product_id,
        expected_title=odoo_title,
        expected_description_html=odoo_description_html,
        expected_condition_code=alternate_condition_code,
        label="odoo-to-shopify",
    )
    wait_for_related_syncs_to_quiet(
        client,
        since_timestamp=odoo_to_shopify_marker,
        modes=ROUNDTRIP_SYNC_MODES,
        label="post odoo-to-shopify settle",
    )

    shopify_to_odoo_marker = _current_utc_timestamp()
    update_shopify_product_snapshot(
        settings,
        shopify_product_id,
        title=shopify_title,
        description_html=shopify_description_html,
        condition_code=original_condition_code,
        condition_metafield_id=shopify_snapshot_after_export.condition_metafield_id,
    )
    import_sync_id = create_sync(client, "import_one_product", {"shopify_product_id_to_sync": shopify_product_id})
    import_sync = wait_for_sync(client, import_sync_id, "remote import_one_product")
    odoo_snapshot_after_import = wait_for_odoo_snapshot(
        client,
        product_id,
        expected_title=shopify_title,
        expected_description_html=shopify_description_html,
        expected_condition_code=original_condition_code,
        label="shopify-to-odoo",
    )
    wait_for_related_syncs_to_quiet(
        client,
        since_timestamp=shopify_to_odoo_marker,
        modes=ROUNDTRIP_SYNC_MODES,
        label="post shopify-to-odoo settle",
    )

    restore_marker = _current_utc_timestamp()
    restore_values: dict[str, object] = {"name": original_title, "website_description": original_description_html}
    if original_condition_id is not None:
        restore_values["condition"] = original_condition_id
    client.execute("product.product", "write", [[product_id], restore_values])
    restore_sync_mode = "export_changed_products"
    restore_sync_values: dict[str, object] | None = None
    restore_label = "remote restore original title"
    if profile == "smoke":
        restore_sync_mode = "export_batch_products"
        restore_sync_values = {"odoo_products_to_sync": [[6, 0, [product_id]]]}
        restore_label = "remote export_batch_products (restore original product state)"
    restore_sync_id = create_sync(client, restore_sync_mode, restore_sync_values)
    restore_sync = wait_for_sync(client, restore_sync_id, restore_label)
    if profile == "smoke":
        assert_sync_count_at_most(restore_sync, maximum_count=1, label=restore_label)
    wait_for_shopify_snapshot(
        settings,
        shopify_product_id,
        expected_title=original_title,
        expected_description_html=original_description_html,
        expected_condition_code=original_condition_code,
        label="restore original product state",
    )
    wait_for_related_syncs_to_quiet(
        client,
        since_timestamp=restore_marker,
        modes=ROUNDTRIP_SYNC_MODES,
        label="post restore settle",
    )

    return {
        "candidate_product_id": product_id,
        "shopify_product_id": shopify_product_id,
        "original_title": original_title,
        "original_description_html": original_description_html,
        "original_condition_code": original_condition_code,
        "odoo_to_shopify_title": odoo_title,
        "odoo_to_shopify_description_html": odoo_description_html,
        "odoo_to_shopify_condition_code": alternate_condition_code,
        "shopify_to_odoo_title": shopify_title,
        "shopify_to_odoo_description_html": shopify_description_html,
        "shopify_to_odoo_condition_code": original_condition_code,
        "shopify_snapshot_after_export": {
            "title": shopify_snapshot_after_export.title,
            "description_html": shopify_snapshot_after_export.description_html,
            "condition_code": shopify_snapshot_after_export.condition_code,
        },
        "odoo_snapshot_after_import": {
            "title": odoo_snapshot_after_import.title,
            "description_html": odoo_snapshot_after_import.description_html,
            "condition_code": odoo_snapshot_after_import.condition_code,
        },
        "export_changed_sync": export_changed_sync,
        "import_one_sync": import_sync,
        "restore_sync": restore_sync,
        "remote_odoo_url": settings.odoo_url,
    }


def _find_roundtrip_candidate(client: RemoteOdooClient) -> tuple[ProductSnapshot, str]:
    alternate_condition = select_alternate_condition(client, exclude_condition_id=None)
    if alternate_condition is None:
        raise RuntimeError("No alternate Shopify-linked product.condition found for validator metafield coverage")

    for candidate_row in search_export_candidates(client):
        candidate_product_id = candidate_row.get("id")
        if not isinstance(candidate_product_id, int):
            continue
        product_snapshot = read_product_snapshot(client, candidate_product_id)
        if not product_snapshot.condition_id or not product_snapshot.condition_code:
            continue
        alternate_for_product = select_alternate_condition(client, exclude_condition_id=product_snapshot.condition_id)
        if alternate_for_product is None:
            continue
        shopify_product_id = get_external_system_id(client, product_snapshot.product_id, "product")
        return product_snapshot, shopify_product_id

    raise RuntimeError("No Shopify-linked product with a restorable condition metafield was found for round-trip validation")


def _select_roundtrip_product(
    client: RemoteOdooClient,
    *,
    profile: str,
    sample_size: int,
) -> RoundtripProductSelection:
    product_snapshot, shopify_product_id = _find_roundtrip_candidate(client)

    if profile == "smoke":
        candidate_product_ids = []
        for candidate_row in search_export_candidates(client):
            candidate_product_id = candidate_row.get("id")
            if isinstance(candidate_product_id, int):
                candidate_product_ids.append(candidate_product_id)
        export_product_ids = _sample_product_ids(candidate_product_ids, sample_size=sample_size)
        export_product_ids = _inject_primary_product_id(
            export_product_ids,
            primary_product_id=product_snapshot.product_id,
            sample_size=sample_size,
        )
    else:
        export_product_ids = (product_snapshot.product_id,)

    return RoundtripProductSelection(
        product_snapshot=product_snapshot,
        shopify_product_id=shopify_product_id,
        export_product_ids=export_product_ids,
    )


def run_roundtrip(
    settings: RemoteShopifySettings,
    *,
    profile: str = "full",
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    start_after_export: bool = False,
    client: RemoteOdooClient | None = None,
) -> dict[str, object]:
    client = client or RemoteOdooClient(settings)
    if start_after_export:
        selection = _select_roundtrip_product(client, profile=profile, sample_size=sample_size)
        resumed_results = _run_roundtrip_for_product(
            client,
            settings,
            product_snapshot=selection.product_snapshot,
            shopify_product_id=selection.shopify_product_id,
            profile=profile,
        )
        resumed_results["start_mode"] = "after_export"
        resumed_results["profile"] = profile
        return resumed_results

    selection = _select_roundtrip_product(client, profile=profile, sample_size=sample_size)

    prepare_marker = _current_utc_timestamp()
    reset_sync_id = create_sync(client, "reset_shopify")
    reset_sync = wait_for_sync(client, reset_sync_id, "remote reset_shopify")
    if profile == "smoke":
        ensure_no_conflicting_syncs(client, clear_conflicts=True)
    prepare_sync_mode = "export_all_products"
    prepare_sync_values: dict[str, object] | None = None
    prepare_sync_label = "remote export_all_products"
    if profile == "smoke":
        prepare_sync_mode = "export_batch_products"
        prepare_sync_values = {"odoo_products_to_sync": [[6, 0, list(selection.export_product_ids)]]}
        prepare_sync_label = "remote export_batch_products"
    export_sync_id = create_sync(client, prepare_sync_mode, prepare_sync_values)
    export_sync = wait_for_sync(client, export_sync_id, prepare_sync_label)
    if profile == "smoke":
        assert_sync_count_at_most(export_sync, maximum_count=len(selection.export_product_ids), label=prepare_sync_label)
    wait_for_related_syncs_to_quiet(
        client,
        since_timestamp=prepare_marker,
        modes=PREPARE_SYNC_MODES,
        label="post prepare settle",
    )
    if profile == "smoke":
        stamp_non_sample_products_as_exported_for_validation(
            client,
            keep_product_ids=selection.export_product_ids,
        )
    updated_shopify_product_id = get_external_system_id(client, selection.product_snapshot.product_id, "product")
    if updated_shopify_product_id:
        selection = RoundtripProductSelection(
            product_snapshot=selection.product_snapshot,
            shopify_product_id=updated_shopify_product_id,
            export_product_ids=selection.export_product_ids,
        )
    resumed_results = _run_roundtrip_for_product(
        client,
        settings,
        product_snapshot=selection.product_snapshot,
        shopify_product_id=selection.shopify_product_id,
        profile=profile,
    )
    resumed_results["reset_sync"] = reset_sync
    resumed_results["export_all_sync"] = export_sync
    resumed_results["start_mode"] = "full"
    resumed_results["profile"] = profile
    resumed_results["prepare_sync_mode"] = prepare_sync_mode
    if profile == "smoke":
        resumed_results["export_sample_product_ids"] = list(selection.export_product_ids)
    return resumed_results


def run_validation_command(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    profile: str = "full",
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    clear_conflicting_syncs: bool = False,
    start_after_export: bool = False,
    repository_root: Path | None = None,
) -> dict[str, object]:
    if profile == "full" and sample_size != DEFAULT_SAMPLE_SIZE:
        raise click.ClickException("--sample-size is only supported with --profile smoke")
    if instance_name == "prod":
        raise click.ClickException("shopify-roundtrip is disabled on prod because it performs destructive and mutating validation")

    effective_repository_root = repository_root or discover_repo_root(Path.cwd())
    settings = load_settings(
        repository_root=effective_repository_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        remote_login=remote_login,
    )
    client = RemoteOdooClient(settings)
    validation_results: dict[str, object] | None = None
    dispatcher_was_active = False
    original_webhook_pause_value: str | None = None
    original_autoschedule_pause_value: str | None = None
    dispatcher_pause_applied = False
    webhook_pause_applied = False
    autoschedule_pause_applied = False
    try:
        dispatcher_was_active = pause_dispatcher_cron(client)
        dispatcher_pause_applied = True
        original_autoschedule_pause_value = pause_sync_autoschedule(client)
        autoschedule_pause_applied = True
        original_webhook_pause_value = pause_webhook_processing(client)
        webhook_pause_applied = True
        ensure_no_conflicting_syncs(client, clear_conflicts=clear_conflicting_syncs)
        validation_results = run_roundtrip(
            settings,
            profile=profile,
            sample_size=sample_size,
            start_after_export=start_after_export,
            client=client,
        )
    finally:
        if webhook_pause_applied:
            restore_webhook_processing(client, original_value=original_webhook_pause_value)
        if autoschedule_pause_applied:
            restore_sync_autoschedule(client, original_value=original_autoschedule_pause_value)
        if dispatcher_pause_applied:
            restore_dispatcher_cron(client, originally_active=dispatcher_was_active)

    if validation_results is None:
        raise RuntimeError("Shopify validation finished without producing a result payload")

    runtime_state = read_validation_runtime_state(client)
    validation_results["post_validation_runtime_state"] = runtime_state
    validation_results["operator_summary"] = _build_operator_summary(
        context_name=context_name,
        instance_name=instance_name,
        results=validation_results,
        runtime_state=runtime_state,
        sample_size=sample_size,
    )
    return validation_results


@click.command()
@click.option("--context", "context_name", default="opw", show_default=True)
@click.option(
    "--instance",
    "instance_name",
    type=click.Choice(SUPPORTED_REMOTE_INSTANCES, case_sensitive=False),
    default="testing",
    show_default=True,
)
@click.option("--env-file", type=click.Path(path_type=Path), default=None)
@click.option("--remote-login", default=DEFAULT_REMOTE_LOGIN, show_default=True)
@click.option("--profile", type=click.Choice(VALIDATION_PROFILES, case_sensitive=False), default="full", show_default=True)
@click.option("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE, show_default=True)
@click.option("--clear-conflicting-syncs", is_flag=True, default=False)
@click.option("--start-after-export", is_flag=True, default=False)
def main(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    profile: str,
    sample_size: int,
    clear_conflicting_syncs: bool,
    start_after_export: bool,
) -> None:
    results = run_validation_command(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        remote_login=remote_login,
        profile=profile,
        sample_size=sample_size,
        clear_conflicting_syncs=clear_conflicting_syncs,
        start_after_export=start_after_export,
    )
    operator_summary = results.get("operator_summary")
    if isinstance(operator_summary, dict):
        print(json.dumps({"operator_summary": operator_summary}, sort_keys=True), flush=True)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main.main(args=sys.argv[1:], prog_name="shopify-roundtrip", standalone_mode=True))
