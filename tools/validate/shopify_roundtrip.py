from __future__ import annotations

import json
import sys
import time
import urllib.request
import xmlrpc.client
from dataclasses import dataclass
from pathlib import Path

import click

from tools.platform import dokploy as platform_dokploy
from tools.platform.environment import discover_repo_root, load_dokploy_source_of_truth, load_environment

POLL_SECONDS = 5
SYNC_TIMEOUT_SECONDS = 8 * 60 * 60
TITLE_TIMEOUT_SECONDS = 180
SYNC_SEARCH_CUTOFF_SECONDS = 300
DEFAULT_REMOTE_LOGIN = "gpt-admin"
SUPPORTED_REMOTE_INSTANCES = ("dev", "testing", "prod")


@dataclass(frozen=True)
class RemoteShopifySettings:
    odoo_url: str
    database_name: str
    odoo_password: str
    remote_login: str
    shop_url_key: str
    shopify_api_token: str
    shopify_api_version: str


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
    data = shopify_graphql(
        settings,
        query="query ProductTitle($id: ID!) { product(id: $id) { title } }",
        variables={"id": shopify_product_gid(shopify_product_id)},
    )
    product_payload = data.get("product") or {}
    if not isinstance(product_payload, dict):
        raise RuntimeError("Unexpected Shopify product payload while reading title")
    return product_payload.get("title")


def set_shopify_title(settings: RemoteShopifySettings, shopify_product_id: str, title: str) -> None:
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
            "input": {"title": title},
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


def _correlate_sync_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _fallback_sync_window_start() -> str:
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() - SYNC_SEARCH_CUTOFF_SECONDS),
    )


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
    if isinstance(sync_record, list) and sync_record and isinstance(sync_record[0], int):
        return sync_record[0]
    if isinstance(sync_record, int):
        return sync_record

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
            return existing_sync_id
    raise RuntimeError(f"Failed to create or resolve remote Shopify sync for mode {mode}: {sync_record!r}")


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


def wait_for_shopify_title(settings: RemoteShopifySettings, shopify_product_id: str, expected_title: str, label: str) -> None:
    deadline = time.time() + TITLE_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_title = get_shopify_title(settings, shopify_product_id)
        print(json.dumps({"label": label, "expected_shopify_title": expected_title, "actual_shopify_title": actual_title}), flush=True)
        if actual_title == expected_title:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for Shopify title during {label}")


def wait_for_odoo_title(client: RemoteOdooClient, product_id: int, expected_title: str, label: str) -> None:
    deadline = time.time() + TITLE_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_title = read_product_name(client, product_id)
        print(json.dumps({"label": label, "expected_odoo_title": expected_title, "actual_odoo_title": actual_title}), flush=True)
        if actual_title == expected_title:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for Odoo title during {label}")


def _run_roundtrip_for_product(
    client: RemoteOdooClient,
    settings: RemoteShopifySettings,
    *,
    product_id: int,
    original_title: str,
    shopify_product_id: str,
) -> dict[str, object]:
    timestamp = int(time.time())
    odoo_title = f"{original_title} [Odoo RPC {timestamp}]"
    shopify_title = f"{original_title} [Shopify RPC {timestamp}]"

    client.execute("product.product", "write", [[product_id], {"name": odoo_title}])
    export_changed_sync_id = create_sync(client, "export_changed_products")
    export_changed_sync = wait_for_sync(client, export_changed_sync_id, "remote export_changed_products")
    wait_for_shopify_title(settings, shopify_product_id, odoo_title, "odoo-to-shopify")

    set_shopify_title(settings, shopify_product_id, shopify_title)
    import_sync_id = create_sync(client, "import_one_product", {"shopify_product_id_to_sync": shopify_product_id})
    import_sync = wait_for_sync(client, import_sync_id, "remote import_one_product")
    wait_for_odoo_title(client, product_id, shopify_title, "shopify-to-odoo")

    client.execute("product.product", "write", [[product_id], {"name": original_title}])
    restore_sync_id = create_sync(client, "export_changed_products")
    restore_sync = wait_for_sync(client, restore_sync_id, "remote restore original title")
    wait_for_shopify_title(settings, shopify_product_id, original_title, "restore original title")

    return {
        "candidate_product_id": product_id,
        "shopify_product_id": shopify_product_id,
        "original_title": original_title,
        "export_changed_sync": export_changed_sync,
        "import_one_sync": import_sync,
        "restore_sync": restore_sync,
        "remote_odoo_url": settings.odoo_url,
    }


def _select_roundtrip_product(client: RemoteOdooClient) -> tuple[int, str, str]:
    candidate = search_export_candidate(client)
    product_id_value = candidate.get("id")
    original_title_value = candidate.get("name")
    if not isinstance(product_id_value, int):
        raise RuntimeError(f"Unexpected candidate product id payload: {candidate!r}")
    product_id = product_id_value
    original_title = str(original_title_value or "")
    shopify_product_id = get_external_system_id(client, product_id, "product")
    return product_id, original_title, shopify_product_id


def run_roundtrip(settings: RemoteShopifySettings, *, start_after_export: bool = False) -> dict[str, object]:
    client = RemoteOdooClient(settings)
    if start_after_export:
        product_id, original_title, shopify_product_id = _select_roundtrip_product(client)
        resumed_results = _run_roundtrip_for_product(
            client,
            settings,
            product_id=product_id,
            original_title=original_title,
            shopify_product_id=shopify_product_id,
        )
        resumed_results["start_mode"] = "after_export"
        return resumed_results

    product_id, original_title, shopify_product_id = _select_roundtrip_product(client)

    reset_sync_id = create_sync(client, "reset_shopify")
    reset_sync = wait_for_sync(client, reset_sync_id, "remote reset_shopify")
    export_sync_id = create_sync(client, "export_all_products")
    export_sync = wait_for_sync(client, export_sync_id, "remote export_all_products")
    updated_shopify_product_id = get_external_system_id(client, product_id, "product")
    if updated_shopify_product_id:
        shopify_product_id = updated_shopify_product_id
    resumed_results = _run_roundtrip_for_product(
        client,
        settings,
        product_id=product_id,
        original_title=original_title,
        shopify_product_id=shopify_product_id,
    )
    resumed_results["reset_sync"] = reset_sync
    resumed_results["export_all_sync"] = export_sync
    resumed_results["start_mode"] = "full"
    return resumed_results


def run_validation_command(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    start_after_export: bool = False,
    repository_root: Path | None = None,
) -> dict[str, object]:
    effective_repository_root = repository_root or discover_repo_root(Path.cwd())
    settings = load_settings(
        repository_root=effective_repository_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        remote_login=remote_login,
    )
    return run_roundtrip(settings, start_after_export=start_after_export)


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
@click.option("--start-after-export", is_flag=True, default=False)
def main(
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    start_after_export: bool,
) -> None:
    results = run_validation_command(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        remote_login=remote_login,
        start_after_export=start_after_export,
    )
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main.main(args=sys.argv[1:], prog_name="shopify-roundtrip", standalone_mode=True))
