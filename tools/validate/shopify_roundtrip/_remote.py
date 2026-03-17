from __future__ import annotations

import json
import urllib.request
import xmlrpc.client
from decimal import Decimal
from pathlib import Path

import click

from tools.platform import dokploy as platform_dokploy
from tools.platform.environment import load_dokploy_source_of_truth, load_environment

from ._shared import (
    CONDITION_METAFIELD_KEY,
    SHOPIFY_METAFIELD_NAMESPACE,
    ProductSnapshot,
    RemoteShopifySettings,
    ShopifyProductSnapshot,
    SUPPORTED_REMOTE_INSTANCES,
    VALIDATION_EXPORT_MARKER_OFFSET_SECONDS,
)
from ._shared import _future_utc_timestamp, _to_decimal, _to_int


def _export_candidate_domain() -> list[list[object]]:
    return [
        ["sale_ok", "=", True],
        ["is_ready_for_sale", "=", True],
        ["is_published", "=", True],
        ["website_description", "!=", False],
        ["website_description", "!=", ""],
        ["type", "=", "consu"],
    ]


def _shopify_linked_export_candidate_domain() -> list[list[object]]:
    return [
        *_export_candidate_domain(),
        ["external_ids.system_id.code", "=", "shopify"],
        ["external_ids.resource", "=", "product"],
    ]


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
    database_name = str(environment_values.get("ODOO_DB_NAME", context_name)).strip() or context_name
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
        data=json.dumps({"query": query, "variables": variables}).encode(),
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
            "    status"
            "    totalInventory"
            "    media(first: 250, sortKey: POSITION) {"
            "      nodes {"
            "        status"
            "      }"
            "    }"
            "    variants(first: 1) {"
            "      nodes {"
            "        price"
            "        inventoryItem {"
            "          unitCost { amount }"
            "        }"
            "      }"
            "    }"
            '    metafields(first: 15, namespace: "custom") {'
            "      nodes { id key value }"
            "    }"
            "  }"
            "}"
        ),
        variables={"id": shopify_product_gid(shopify_product_id)},
    )
    product_payload = data.get("product")
    if product_payload is None:
        raise RuntimeError(f"Shopify product {shopify_product_id} was not found while reading product snapshot")
    if not isinstance(product_payload, dict):
        raise RuntimeError("Unexpected Shopify product payload while reading product snapshot")

    condition_metafield_id = None
    condition_code = None
    metafields_payload = product_payload.get("metafields") or {}
    metafield_nodes = metafields_payload.get("nodes") if isinstance(metafields_payload, dict) else []
    if isinstance(metafield_nodes, list):
        for metafield in metafield_nodes:
            if not isinstance(metafield, dict) or metafield.get("key") != CONDITION_METAFIELD_KEY:
                continue
            metafield_id = metafield.get("id")
            metafield_value = metafield.get("value")
            condition_metafield_id = str(metafield_id) if metafield_id else None
            condition_code = str(metafield_value) if metafield_value is not None else None
            break

    media_payload = product_payload.get("media") or {}
    media_nodes = media_payload.get("nodes") if isinstance(media_payload, dict) else []
    media_count = len([node for node in media_nodes if isinstance(node, dict)]) if isinstance(media_nodes, list) else 0
    failed_media_count = len(
        [node for node in media_nodes if isinstance(node, dict) and str(node.get("status") or "") == "FAILED"]
    ) if isinstance(media_nodes, list) else 0

    variant_price = None
    variant_unit_cost = None
    variants_payload = product_payload.get("variants") or {}
    variant_nodes = variants_payload.get("nodes") if isinstance(variants_payload, dict) else []
    if isinstance(variant_nodes, list) and variant_nodes and isinstance(variant_nodes[0], dict):
        variant_payload = variant_nodes[0]
        variant_price = _to_decimal(variant_payload.get("price"))
        inventory_item_payload = variant_payload.get("inventoryItem") or {}
        unit_cost_payload = inventory_item_payload.get("unitCost") if isinstance(inventory_item_payload, dict) else {}
        if isinstance(unit_cost_payload, dict):
            variant_unit_cost = _to_decimal(unit_cost_payload.get("amount"))

    return ShopifyProductSnapshot(
        title=str(product_payload.get("title")) if product_payload.get("title") is not None else None,
        description_html=str(product_payload.get("descriptionHtml")) if product_payload.get("descriptionHtml") is not None else None,
        condition_metafield_id=condition_metafield_id,
        condition_code=condition_code,
        status=str(product_payload.get("status")) if product_payload.get("status") is not None else None,
        total_inventory=_to_int(product_payload.get("totalInventory")),
        variant_price=variant_price,
        variant_unit_cost=variant_unit_cost,
        media_count=media_count,
        failed_media_count=failed_media_count,
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
        variables={"identifier": {"id": shopify_product_gid(shopify_product_id)}, "input": input_payload},
    )
    response_payload = data.get("productSet") or {}
    if not isinstance(response_payload, dict):
        raise RuntimeError("Unexpected Shopify productSet payload while updating title")
    user_errors = response_payload.get("userErrors") or []
    if user_errors:
        raise RuntimeError(f"Shopify title update failed: {user_errors}")


def search_export_candidates(client: RemoteOdooClient, *, require_shopify_link: bool) -> list[dict[str, object]]:
    domain = _shopify_linked_export_candidate_domain() if require_shopify_link else _export_candidate_domain()
    result = client.execute("product.product", "search_read", [domain], {"fields": ["id", "name"], "order": "id asc"})
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected search_read payload for Shopify export candidates: {result!r}")
    return [row for row in result if isinstance(row, dict)]


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
        [[product_id], ["name", "website_description", "condition", "list_price", "standard_price", "qty_available", "image_count"]],
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
        list_price=Decimal(str(product_payload.get("list_price") or 0)),
        standard_price=Decimal(str(product_payload.get("standard_price") or 0)),
        quantity_available=float(product_payload.get("qty_available") or 0),
        image_count=int(product_payload.get("image_count") or 0),
    )


def stamp_non_sample_products_as_exported_for_validation(client: RemoteOdooClient, *, keep_product_ids: tuple[int, ...]) -> str:
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
    domain: list[list[object]] = [["code", "!=", False]]
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
