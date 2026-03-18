from __future__ import annotations

import json
import sys
import time
import xmlrpc.client
from datetime import UTC, datetime
from pathlib import Path

import click

from tools.platform.environment import discover_repo_root

from . import _remote
from ._remote import (
    RemoteOdooClient,
    _export_candidate_domain,
    _shopify_linked_export_candidate_domain,
    get_external_system_id,
    get_shopify_product_snapshot,
    get_shopify_title,
    load_settings,
    read_product_name,
    read_product_snapshot,
    search_export_candidates,
    select_alternate_condition,
    stamp_non_sample_products_as_exported_for_validation,
    update_shopify_product_snapshot,
)
from ._shared import (
    CONFLICTING_SYNC_STATES,
    CONFLICT_CLEAR_MAX_RETRIES,
    CONFLICT_CLEAR_RETRY_SLEEP_SECONDS,
    DEFAULT_REMOTE_LOGIN,
    DEFAULT_SAMPLE_SIZE,
    DEFAULT_STANDARD_SAMPLE_SIZE,
    FIELD_TIMEOUT_SECONDS,
    POLL_SECONDS,
    PREPARE_SYNC_MODES,
    ProductSnapshot,
    ROUNDTRIP_SYNC_MODES,
    RemoteShopifySettings,
    RoundtripPrepareSelection,
    RoundtripProductSelection,
    SHOPIFY_AUTOSCHEDULE_PAUSE_KEY,
    SHOPIFY_WEBHOOK_PAUSE_KEY,
    SUPPORTED_REMOTE_INSTANCES,
    SYNC_SEARCH_CUTOFF_SECONDS,
    SYNC_SETTLE_QUIET_SECONDS,
    SYNC_SETTLE_TIMEOUT_SECONDS,
    SYNC_TIMEOUT_SECONDS,
    ShopifyProductSnapshot,
    TITLE_TIMEOUT_SECONDS,
    VALIDATION_PROFILES,
    _expected_shopify_status,
    _future_utc_timestamp,
    _normalize_html_fragment,
    _parse_odoo_utc_timestamp,
    _shopify_prepare_snapshot_matches,
    _snapshot_fields_match,
    profile_roundtrip_product_count,
    profile_uses_bounded_prepare,
)


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
            {
                "label": "pause webhook processing",
                "config_parameter": updated_row or {"key": SHOPIFY_WEBHOOK_PAUSE_KEY, "value": None},
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return original_value


def restore_webhook_processing(client: RemoteOdooClient, *, original_value: str | None) -> None:
    restored_row = set_config_parameter(client, SHOPIFY_WEBHOOK_PAUSE_KEY, original_value)
    print(
        json.dumps(
            {
                "label": "restore webhook processing",
                "config_parameter": restored_row or {"key": SHOPIFY_WEBHOOK_PAUSE_KEY, "value": None},
            },
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
            {
                "label": "pause Shopify autoschedule",
                "config_parameter": updated_row or {"key": SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": None},
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return original_value


def restore_sync_autoschedule(client: RemoteOdooClient, *, original_value: str | None) -> None:
    restored_row = set_config_parameter(client, SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, original_value)
    print(
        json.dumps(
            {
                "label": "restore Shopify autoschedule",
                "config_parameter": restored_row or {"key": SHOPIFY_AUTOSCHEDULE_PAUSE_KEY, "value": None},
            },
            sort_keys=True,
        ),
        flush=True,
    )


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
) -> dict[str, object]:
    def _sync_id(key: str) -> int | None:
        value = results.get(key)
        if isinstance(value, dict):
            sync_id = value.get("id")
            if isinstance(sync_id, int):
                return sync_id
        return None

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
    export_sample_count = len(export_sample_product_ids) if isinstance(export_sample_product_ids, list) else None
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
        "reset_sync_id": _sync_id("reset_sync"),
        "prepare_sync_id": _sync_id("export_all_sync"),
        "odoo_to_shopify_sync_id": _sync_id("export_changed_sync"),
        "shopify_to_odoo_sync_id": _sync_id("import_one_sync"),
        "restore_sync_id": _sync_id("restore_sync"),
        "checks_completed": checks_completed,
        "post_validation_active_sync_count": active_sync_count,
    }


def _is_serialization_failure_fault(exception: xmlrpc.client.Fault) -> bool:
    fault_text = f"{exception.faultCode} {exception.faultString}".lower()
    return "serializationfailure" in fault_text or "could not serialize access due to concurrent update" in fault_text


def _write_conflicting_sync(
    client: RemoteOdooClient,
    *,
    sync_id: int,
    values: dict[str, object],
) -> None:
    for attempt in range(1, CONFLICT_CLEAR_MAX_RETRIES + 1):
        try:
            client.execute("shopify.sync", "write", [[sync_id], values])
            return
        except xmlrpc.client.Fault as exception:
            if not _is_serialization_failure_fault(exception) or attempt >= CONFLICT_CLEAR_MAX_RETRIES:
                raise
            sleep_seconds = CONFLICT_CLEAR_RETRY_SLEEP_SECONDS * attempt
            print(
                json.dumps(
                    {
                        "label": "retry clear conflicting syncs",
                        "sync_id": sync_id,
                        "attempt": attempt,
                        "max_retries": CONFLICT_CLEAR_MAX_RETRIES,
                        "sleep_seconds": sleep_seconds,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            time.sleep(sleep_seconds)


def clear_conflicting_syncs(client: RemoteOdooClient, *, reason: str) -> list[int]:
    # Cancel each sync independently so one concurrent row update does not force
    # a bulk rewrite retry across the whole conflicting set.
    conflicting_syncs = list_conflicting_syncs(client)
    conflicting_sync_ids: list[int] = []
    for row in conflicting_syncs:
        sync_id = row.get("id")
        if not isinstance(sync_id, int):
            continue
        conflicting_sync_ids.append(sync_id)
        state_value = str(row.get("state") or "")
        if state_value == "queued":
            _write_conflicting_sync(
                client,
                sync_id=sync_id,
                values={"state": "canceled", "error_message": reason},
            )
        elif state_value == "running":
            _write_conflicting_sync(
                client,
                sync_id=sync_id,
                values={"cancel_requested": True, "cancel_reason": reason},
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


def _inject_primary_product_id(
    sampled_product_ids: tuple[int, ...], *, primary_product_id: int, sample_size: int
) -> tuple[int, ...]:
    if primary_product_id in sampled_product_ids:
        return sampled_product_ids
    adjusted_product_ids = (primary_product_id, *tuple(pid for pid in sampled_product_ids if pid != primary_product_id))
    return adjusted_product_ids[:sample_size]


def _correlate_sync_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _fallback_sync_window_start() -> str:
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.gmtime(time.time() - SYNC_SEARCH_CUTOFF_SECONDS),
    )


def _current_utc_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


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
            f"Unexpected sync size during {label}: expected at most {maximum_count}, got {total_count}. Sync state: {sync_state}"
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
        print(
            json.dumps({"label": label, "expected_shopify_title": expected_title, "actual_shopify_title": actual_title}), flush=True
        )
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
        if not _snapshot_fields_match(
            actual_title=actual_snapshot.title,
            actual_description_html=actual_snapshot.description_html,
            actual_condition_code=actual_snapshot.condition_code,
            expected_title=expected_title,
            expected_description_html=expected_description_html,
            expected_condition_code=expected_condition_code,
        ):
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
        if not _snapshot_fields_match(
            actual_title=actual_snapshot.title,
            actual_description_html=actual_snapshot.description_html,
            actual_condition_code=actual_snapshot.condition_code,
            expected_title=expected_title,
            expected_description_html=expected_description_html,
            expected_condition_code=expected_condition_code,
        ):
            time.sleep(POLL_SECONDS)
            continue
        return actual_snapshot
    raise RuntimeError(f"Timed out waiting for Odoo product snapshot during {label}")


def wait_for_shopify_prepare_snapshot(
    settings: RemoteShopifySettings,
    shopify_product_id: str,
    *,
    product_snapshot: ProductSnapshot,
    label: str,
) -> ShopifyProductSnapshot:
    deadline = time.time() + FIELD_TIMEOUT_SECONDS
    while time.time() < deadline:
        actual_snapshot = get_shopify_product_snapshot(settings, shopify_product_id)
        print(
            json.dumps(
                {
                    "label": label,
                    "expected_shopify_status": _expected_shopify_status(product_snapshot),
                    "actual_shopify_status": actual_snapshot.status,
                    "expected_shopify_total_inventory": int(product_snapshot.quantity_available),
                    "actual_shopify_total_inventory": actual_snapshot.total_inventory,
                    "expected_shopify_variant_price": str(product_snapshot.list_price),
                    "actual_shopify_variant_price": str(actual_snapshot.variant_price) if actual_snapshot.variant_price is not None else None,
                    "expected_shopify_variant_unit_cost": str(product_snapshot.standard_price),
                    "actual_shopify_variant_unit_cost": (
                        str(actual_snapshot.variant_unit_cost) if actual_snapshot.variant_unit_cost is not None else None
                    ),
                    "expected_shopify_media_count": product_snapshot.image_count,
                    "actual_shopify_media_count": actual_snapshot.media_count,
                    "actual_shopify_failed_media_count": actual_snapshot.failed_media_count,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if _shopify_prepare_snapshot_matches(actual_snapshot=actual_snapshot, product_snapshot=product_snapshot):
            return actual_snapshot
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for Shopify prepare snapshot during {label}")


def verify_prepare_export_sample(
    client: RemoteOdooClient,
    settings: RemoteShopifySettings,
    *,
    product_id: int,
    label: str,
) -> dict[str, object]:
    product_snapshot = read_product_snapshot(client, product_id)
    shopify_product_id = get_external_system_id(client, product_id, "product")
    shopify_snapshot = wait_for_shopify_prepare_snapshot(
        settings,
        shopify_product_id,
        product_snapshot=product_snapshot,
        label=label,
    )
    return {
        "product_id": product_id,
        "shopify_product_id": shopify_product_id,
        "status": shopify_snapshot.status,
        "total_inventory": shopify_snapshot.total_inventory,
        "variant_price": str(shopify_snapshot.variant_price) if shopify_snapshot.variant_price is not None else None,
        "variant_unit_cost": str(shopify_snapshot.variant_unit_cost) if shopify_snapshot.variant_unit_cost is not None else None,
        "media_count": shopify_snapshot.media_count,
        "failed_media_count": shopify_snapshot.failed_media_count,
    }


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
    if profile_uses_bounded_prepare(profile):
        export_changed_sync_mode = "export_batch_products"
        export_changed_sync_values = {"odoo_products_to_sync": [[6, 0, [product_id]]]}
        export_changed_label = "remote export_batch_products (odoo-to-shopify)"
    export_changed_sync_id = create_sync(client, export_changed_sync_mode, export_changed_sync_values)
    export_changed_sync = wait_for_sync(client, export_changed_sync_id, export_changed_label)
    if profile_uses_bounded_prepare(profile):
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
    if profile_uses_bounded_prepare(profile):
        restore_sync_mode = "export_batch_products"
        restore_sync_values = {"odoo_products_to_sync": [[6, 0, [product_id]]]}
        restore_label = "remote export_batch_products (restore original product state)"
    restore_sync_id = create_sync(client, restore_sync_mode, restore_sync_values)
    restore_sync = wait_for_sync(client, restore_sync_id, restore_label)
    if profile_uses_bounded_prepare(profile):
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


def _find_candidate_snapshot(
    client: RemoteOdooClient,
    *,
    require_shopify_link: bool,
    missing_message: str,
) -> ProductSnapshot:
    alternate_condition = select_alternate_condition(client, exclude_condition_id=None)
    if alternate_condition is None:
        raise RuntimeError("No alternate Shopify-linked product.condition found for validator metafield coverage")

    fallback_snapshot: ProductSnapshot | None = None
    for candidate_row in search_export_candidates(client, require_shopify_link=require_shopify_link):
        candidate_product_id = candidate_row.get("id")
        if not isinstance(candidate_product_id, int):
            continue
        product_snapshot = read_product_snapshot(client, candidate_product_id)
        if not product_snapshot.condition_id or not product_snapshot.condition_code:
            continue
        alternate_for_product = select_alternate_condition(client, exclude_condition_id=product_snapshot.condition_id)
        if alternate_for_product is None:
            continue
        if product_snapshot.image_count > 0:
            return product_snapshot
        if fallback_snapshot is None:
            fallback_snapshot = product_snapshot

    if fallback_snapshot is not None:
        return fallback_snapshot

    raise RuntimeError(missing_message)


def _find_roundtrip_candidate(client: RemoteOdooClient) -> tuple[ProductSnapshot, str]:
    product_snapshot = _find_candidate_snapshot(
        client,
        require_shopify_link=True,
        missing_message="No Shopify-linked product with a restorable condition metafield was found for round-trip validation",
    )
    shopify_product_id = get_external_system_id(client, product_snapshot.product_id, "product")
    return product_snapshot, shopify_product_id


def _find_prepare_candidate(client: RemoteOdooClient) -> ProductSnapshot:
    return _find_candidate_snapshot(
        client,
        require_shopify_link=False,
        missing_message="No exportable product with a restorable condition metafield was found for round-trip validation",
    )


def _select_roundtrip_prepare_selection(
    client: RemoteOdooClient,
    *,
    profile: str,
    sample_size: int,
    require_shopify_link: bool = False,
) -> RoundtripPrepareSelection:
    product_snapshot = _find_candidate_snapshot(
        client,
        require_shopify_link=require_shopify_link,
        missing_message=(
            "No Shopify-linked product with a restorable condition metafield was found for round-trip validation"
            if require_shopify_link
            else "No exportable product with a restorable condition metafield was found for round-trip validation"
        ),
    )

    if profile_uses_bounded_prepare(profile):
        candidate_product_ids = []
        for candidate_row in search_export_candidates(client, require_shopify_link=require_shopify_link):
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

    return RoundtripPrepareSelection(
        product_snapshot=product_snapshot,
        export_product_ids=export_product_ids,
    )


def _execute_roundtrip_products(
    client: RemoteOdooClient,
    settings: RemoteShopifySettings,
    *,
    profile: str,
    product_ids: tuple[int, ...] | list[int],
    primary_snapshot: ProductSnapshot | None = None,
) -> list[dict[str, object]]:
    roundtrip_results: list[dict[str, object]] = []
    primary_product_id = primary_snapshot.product_id if primary_snapshot else None
    for roundtrip_product_id in product_ids:
        if primary_product_id is not None and roundtrip_product_id == primary_product_id:
            assert primary_snapshot is not None
            roundtrip_product_snapshot = primary_snapshot
        else:
            roundtrip_product_snapshot = read_product_snapshot(client, roundtrip_product_id)
        roundtrip_shopify_product_id = get_external_system_id(client, roundtrip_product_id, "product")
        roundtrip_results.append(
            _run_roundtrip_for_product(
                client,
                settings,
                product_snapshot=roundtrip_product_snapshot,
                shopify_product_id=roundtrip_shopify_product_id,
                profile=profile,
            )
        )
    return roundtrip_results


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
        prepare_selection = _select_roundtrip_prepare_selection(
            client,
            profile=profile,
            sample_size=sample_size,
            require_shopify_link=True,
        )
        roundtrip_product_ids = list(prepare_selection.export_product_ids[: profile_roundtrip_product_count(profile)])
        roundtrip_results = _execute_roundtrip_products(
            client,
            settings,
            profile=profile,
            product_ids=roundtrip_product_ids,
            primary_snapshot=prepare_selection.product_snapshot,
        )
        resumed_results = roundtrip_results[0]
        resumed_results["start_mode"] = "after_export"
        resumed_results["profile"] = profile
        if len(roundtrip_results) > 1:
            resumed_results["additional_roundtrip_results"] = roundtrip_results[1:]
        return resumed_results

    prepare_selection = _select_roundtrip_prepare_selection(client, profile=profile, sample_size=sample_size)

    prepare_marker = _current_utc_timestamp()
    reset_sync_id = create_sync(client, "reset_shopify")
    reset_sync = wait_for_sync(client, reset_sync_id, "remote reset_shopify")
    if profile_uses_bounded_prepare(profile):
        ensure_no_conflicting_syncs(client, clear_conflicts=True)
    prepare_sync_mode = "export_all_products"
    prepare_sync_values: dict[str, object] | None = None
    prepare_sync_label = "remote export_all_products"
    if profile_uses_bounded_prepare(profile):
        prepare_sync_mode = "export_batch_products"
        prepare_sync_values = {"odoo_products_to_sync": [[6, 0, list(prepare_selection.export_product_ids)]]}
        prepare_sync_label = "remote export_batch_products"
    export_sync_id = create_sync(client, prepare_sync_mode, prepare_sync_values)
    export_sync = wait_for_sync(client, export_sync_id, prepare_sync_label)
    if profile_uses_bounded_prepare(profile):
        assert_sync_count_at_most(export_sync, maximum_count=len(prepare_selection.export_product_ids), label=prepare_sync_label)
    wait_for_related_syncs_to_quiet(
        client,
        since_timestamp=prepare_marker,
        modes=PREPARE_SYNC_MODES,
        label="post prepare settle",
    )
    if profile_uses_bounded_prepare(profile):
        stamp_non_sample_products_as_exported_for_validation(
            client,
            keep_product_ids=prepare_selection.export_product_ids,
        )
    prepared_sample_results = [
        verify_prepare_export_sample(
            client,
            settings,
            product_id=sample_product_id,
            label=f"prepare export product {sample_product_id}",
        )
        for sample_product_id in prepare_selection.export_product_ids
    ]
    roundtrip_product_ids = list(prepare_selection.export_product_ids[: profile_roundtrip_product_count(profile)])
    roundtrip_results = _execute_roundtrip_products(
        client,
        settings,
        profile=profile,
        product_ids=roundtrip_product_ids,
        primary_snapshot=prepare_selection.product_snapshot,
    )
    resumed_results = roundtrip_results[0]
    resumed_results["reset_sync"] = reset_sync
    resumed_results["export_all_sync"] = export_sync
    resumed_results["start_mode"] = "prepared"
    resumed_results["profile"] = profile
    resumed_results["prepare_sync_mode"] = prepare_sync_mode
    resumed_results["prepared_sample_results"] = prepared_sample_results
    if profile_uses_bounded_prepare(profile):
        resumed_results["export_sample_product_ids"] = list(prepare_selection.export_product_ids)
    if len(roundtrip_results) > 1:
        resumed_results["additional_roundtrip_results"] = roundtrip_results[1:]
    return resumed_results


def run_validation_command(
    *,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    remote_login: str,
    profile: str = "full",
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    clear_conflicts: bool = False,
    start_after_export: bool = False,
    repository_root: Path | None = None,
) -> dict[str, object]:
    if instance_name == "prod":
        raise click.ClickException("shopify-roundtrip is disabled on prod because it performs destructive and mutating validation")
    if not profile_uses_bounded_prepare(profile) and sample_size != DEFAULT_SAMPLE_SIZE:
        raise click.ClickException("--sample-size is only supported with --profile smoke or --profile standard")
    if profile == "standard" and sample_size == DEFAULT_SAMPLE_SIZE:
        sample_size = DEFAULT_STANDARD_SAMPLE_SIZE

    effective_repository_root = repository_root or discover_repo_root(Path.cwd())
    settings = load_settings(
        repository_root=effective_repository_root,
        env_file=env_file,
        context_name=context_name,
        instance_name=instance_name,
        remote_login=remote_login,
    )
    client = RemoteOdooClient(settings)
    original_webhook_pause_value: str | None = None
    original_autoschedule_pause_value: str | None = None
    webhook_pause_applied = False
    autoschedule_pause_applied = False
    try:
        original_autoschedule_pause_value = pause_sync_autoschedule(client)
        autoschedule_pause_applied = True
        original_webhook_pause_value = pause_webhook_processing(client)
        webhook_pause_applied = True
        ensure_no_conflicting_syncs(client, clear_conflicts=clear_conflicts)
        results = run_roundtrip(
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

    runtime_state = read_validation_runtime_state(client)
    results["post_validation_runtime_state"] = runtime_state
    results["operator_summary"] = _build_operator_summary(
        context_name=context_name,
        instance_name=instance_name,
        results=results,
        runtime_state=runtime_state,
    )
    return results


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
    clear_conflicts: bool,
    start_after_export: bool,
) -> None:
    results = run_validation_command(
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        remote_login=remote_login,
        profile=profile,
        sample_size=sample_size,
        clear_conflicts=clear_conflicts,
        start_after_export=start_after_export,
    )
    operator_summary = results.get("operator_summary")
    if isinstance(operator_summary, dict):
        print(json.dumps({"operator_summary": operator_summary}, sort_keys=True), flush=True)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main.main(args=sys.argv[1:], prog_name="shopify-roundtrip"))
