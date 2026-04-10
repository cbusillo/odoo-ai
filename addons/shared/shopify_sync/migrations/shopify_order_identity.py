import logging
from collections.abc import Callable

from odoo import api
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)

ORDER_RESOURCE = "order"
ORDER_LINE_RESOURCE = "order_line"

SHIPSTATION_SYSTEM_CODE = "shipstation"
SHIPSTATION_SYSTEM_NAME = "ShipStation"
SHIPSTATION_SYSTEM_URL = "https://shipstation.com"
SHIPSTATION_SYSTEM_SEQUENCE = 60


def migrate_shopify_order_identity_external_ids(env: api.Environment) -> None:
    drop_candidates_by_table: dict[str, set[str]] = {}
    drop_candidates_by_table.setdefault("sale_order", set()).update(
        _migrate_external_ids(
            env,
            system_code="shopify",
            model_name="sale.order",
            table_name="sale_order",
            field_resource_map={"shopify_order_id": ORDER_RESOURCE},
            normalize_external_ids=_normalize_shopify_external_id,
        )
    )
    drop_candidates_by_table.setdefault("sale_order_line", set()).update(
        _migrate_external_ids(
            env,
            system_code="shopify",
            model_name="sale.order.line",
            table_name="sale_order_line",
            field_resource_map={"shopify_order_line_id": ORDER_LINE_RESOURCE},
        )
    )
    drop_candidates_by_table.setdefault("sale_order", set()).update(
        _migrate_external_ids(
            env,
            system_code="ebay",
            model_name="sale.order",
            table_name="sale_order",
            field_resource_map={"ebay_order_id": ORDER_RESOURCE},
        )
    )
    _drop_legacy_order_identity_columns(env, drop_candidates_by_table)


def migrate_shipstation_order_identity_external_ids(env: api.Environment) -> None:
    env["external.system"].ensure_system(
        code=SHIPSTATION_SYSTEM_CODE,
        name=SHIPSTATION_SYSTEM_NAME,
        id_format=r"^.+$",
        sequence=SHIPSTATION_SYSTEM_SEQUENCE,
        url=SHIPSTATION_SYSTEM_URL,
        active=True,
    )
    drop_candidates_by_table = {
        "sale_order": _migrate_external_ids(
            env,
            system_code=SHIPSTATION_SYSTEM_CODE,
            model_name="sale.order",
            table_name="sale_order",
            field_resource_map={"shipstation_order_id": ORDER_RESOURCE},
        )
    }
    _drop_legacy_order_identity_columns(
        env,
        drop_candidates_by_table,
        drop_map={"sale_order": ["shipstation_order_id"]},
    )


def _drop_legacy_order_identity_columns(
    env: api.Environment,
    drop_candidates_by_table: dict[str, set[str]],
    *,
    drop_map: dict[str, list[str]] | None = None,
) -> None:
    drop_map = drop_map or {
        "sale_order": ["shopify_order_id", "ebay_order_id"],
        "sale_order_line": ["shopify_order_line_id"],
    }
    for table_name, column_names in drop_map.items():
        allowed_columns = drop_candidates_by_table.get(table_name, set())
        if not allowed_columns:
            continue
        scoped_columns = [column_name for column_name in column_names if column_name in allowed_columns]
        if not scoped_columns:
            continue
        existing_columns = _filter_existing_columns(env.cr, table_name, scoped_columns)
        if not existing_columns:
            continue
        drop_clauses = ", ".join([f"DROP COLUMN IF EXISTS {column_name}" for column_name in existing_columns])
        _logger.info(
            "Dropping legacy Shopify order identity columns from %s: %s",
            table_name,
            ", ".join(existing_columns),
        )
        env.cr.execute(f"ALTER TABLE {table_name} {drop_clauses}")


def _migrate_external_ids(
    env: api.Environment,
    *,
    system_code: str,
    model_name: str,
    table_name: str,
    field_resource_map: dict[str, str],
    normalize_external_ids: Callable[[str], str | None] | None = None,
) -> set[str]:
    external_system = env["external.system"].sudo().search([("code", "=", system_code)], limit=1)
    if not external_system:
        _logger.warning("External system '%s' not found; skipping %s migration", system_code, model_name)
        return set()

    existing_columns = _filter_existing_columns(env.cr, table_name, list(field_resource_map.keys()))
    if not existing_columns:
        return set()

    filtered_map = {column_name: resource for column_name, resource in field_resource_map.items() if column_name in existing_columns}
    if not filtered_map:
        return set()

    drop_candidates = set(filtered_map.keys())
    rows = _fetch_column_values(env.cr, table_name, list(filtered_map.keys()))
    if not rows:
        return drop_candidates

    record_model = env[model_name].sudo().with_context(active_test=False)

    for row in rows:
        res_id = row[0]
        record = record_model.browse(res_id).exists()
        if not record:
            continue
        row_values = row[1:]
        for column_name, raw_value in zip(
            filtered_map.keys(),
            row_values,
            strict=len(filtered_map) == len(row_values),
        ):
            if raw_value is None:
                continue
            sanitized_value = (raw_value if isinstance(raw_value, str) else str(raw_value)).strip()
            if not sanitized_value:
                continue

            resource = filtered_map[column_name]
            normalized_external_id: str | None = sanitized_value
            if normalize_external_ids:
                normalized_external_id = normalize_external_ids(sanitized_value)
                if not normalized_external_id:
                    _logger.warning(
                        "Skipping %s external id '%s' for %s (resource %s): invalid format",
                        system_code,
                        sanitized_value,
                        model_name,
                        resource,
                    )
                    drop_candidates.discard(column_name)
                    continue

            if not record.set_external_id(system_code, normalized_external_id, resource):
                _logger.warning(
                    "Skipping duplicate external id '%s' for %s (resource %s): already used by %s",
                    normalized_external_id,
                    model_name,
                    resource,
                    env[model_name].search_by_external_id(system_code, normalized_external_id, resource).id,
                )
                drop_candidates.discard(column_name)

    return drop_candidates


def _fetch_column_values(cr: Cursor, table_name: str, column_names: list[str]) -> list[tuple]:
    if not column_names:
        return []
    where_clause = " OR ".join([f"{column_name} IS NOT NULL AND {column_name} != ''" for column_name in column_names])
    query = f"SELECT id, {', '.join(column_names)} FROM {table_name} WHERE {where_clause}"
    cr.execute(query)
    return cr.fetchall()




def _normalize_shopify_external_id(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    if "?" in candidate:
        candidate = candidate.split("?", 1)[0]
    if candidate.startswith("gid://"):
        candidate = candidate.rsplit("/", 1)[-1]
    digits_only = "".join(character for character in candidate if character.isdigit())
    return digits_only or None


def _filter_existing_columns(cr: Cursor, table_name: str, column_names: list[str]) -> list[str]:
    if not column_names:
        return []
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = ANY(%s)
        """,
        [table_name, column_names],
    )
    existing_columns = {row[0] for row in cr.fetchall()}
    return [column_name for column_name in column_names if column_name in existing_columns]
