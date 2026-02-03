import logging
from datetime import datetime

from odoo import SUPERUSER_ID, api
from odoo.orm.environments import Environment
from odoo.sql_db import Cursor

from .services.shopify.helpers import (
    ADDRESS_RESOURCE_DEFAULT,
    ADDRESS_RESOURCE_DELIVERY,
    ADDRESS_RESOURCE_INVOICE,
)

_logger = logging.getLogger(__name__)


def pre_init_hook(env_or_cursor: Environment | Cursor) -> None:
    cursor = env_or_cursor.cr if isinstance(env_or_cursor, api.Environment) else env_or_cursor
    _ensure_delivery_service_map_xmlids(cursor)
    _deduplicate_delivery_default_codes(cursor)


def post_init_hook(*args: tuple) -> None:
    """
    TODO: Remove this hook after prod is upgraded to Odoo 19 and the legacy
    Shopify/eBay columns are fully retired from all live databases.
    """
    if len(args) == 1:
        env = args[0]
    else:
        cr, _registry = args
        env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_marketplace_external_ids(env)


def _migrate_marketplace_external_ids(env: api.Environment) -> None:
    shopify_system = env["external.system"].sudo().search([("code", "=", "shopify")], limit=1)
    ebay_system = env["external.system"].sudo().search([("code", "=", "ebay")], limit=1)

    drop_candidates_by_table: dict[str, set[str]] = {}

    drop_candidates_by_table.setdefault("res_partner", set()).update(
        _migrate_external_ids_for_system(
            env,
            model_name="res.partner",
            table_name="res_partner",
            system_code="shopify",
            field_resource_map={
                "shopify_customer_id": "customer",
            },
        )
    )
    drop_candidates_by_table.setdefault("res_partner", set()).update(_migrate_shopify_address_ids(env))
    _deduplicate_ebay_usernames(env)
    drop_candidates_by_table.setdefault("res_partner", set()).update(
        _migrate_external_ids_for_system(
            env,
            model_name="res.partner",
            table_name="res_partner",
            system_code="ebay",
            field_resource_map={
                "ebay_username": "profile",
            },
        )
    )
    drop_candidates_by_table.setdefault("product_product", set()).update(
        _migrate_external_ids_for_system(
            env,
            model_name="product.product",
            table_name="product_product",
            system_code="shopify",
            field_resource_map={
                "shopify_variant_id": "variant",
                "shopify_condition_id": "condition",
                "shopify_ebay_category_id": "ebay_category",
            },
        )
    )
    for table_name, column_names in _migrate_template_shopify_product_ids(env).items():
        drop_candidates_by_table.setdefault(table_name, set()).update(column_names)
    _deduplicate_shopify_media_ids(env)
    drop_candidates_by_table.setdefault("product_image", set()).update(
        _migrate_external_ids_for_system(
            env,
            model_name="product.image",
            table_name="product_image",
            system_code="shopify",
            field_resource_map={
                "shopify_media_id": "media",
            },
        )
    )

    _drop_legacy_marketplace_columns(
        env,
        drop_shopify=bool(shopify_system),
        drop_ebay=bool(ebay_system),
        drop_candidates_by_table=drop_candidates_by_table,
    )
    _deduplicate_shopify_address_ids(env)
    _cleanup_legacy_shopify_address_ids(env)


# noinspection SqlResolve
def _deduplicate_shopify_media_ids(env: api.Environment) -> None:
    if not _filter_existing_columns(env.cr, "product_image", ["shopify_media_id"]):
        return

    env.cr.execute(
        """
        SELECT shopify_media_id
          FROM product_image
         WHERE shopify_media_id IS NOT NULL
           AND shopify_media_id != ''
         GROUP BY shopify_media_id
        HAVING COUNT(*) > 1
        """
    )
    duplicate_media_ids = [row[0] for row in env.cr.fetchall()]
    if not duplicate_media_ids:
        return

    for media_id in duplicate_media_ids:
        env.cr.execute(
            """
            SELECT id, product_tmpl_id
              FROM product_image
             WHERE shopify_media_id = %s
             ORDER BY id
            """,
            (media_id,),
        )
        image_rows = env.cr.fetchall()
        template_rows = [row for row in image_rows if row[1]]
        orphan_rows = [row for row in image_rows if not row[1]]
        if len(template_rows) == 1 and orphan_rows:
            orphan_ids = [row[0] for row in orphan_rows]
            env.cr.execute(
                """
                UPDATE product_image
                   SET shopify_media_id = NULL
                 WHERE id = ANY(%s)
                """,
                (orphan_ids,),
            )
            _logger.info(
                "Cleared duplicate Shopify media id '%s' on orphan product_image rows: %s",
                media_id,
                orphan_ids,
            )
            continue
        _logger.warning(
            "Duplicate Shopify media id '%s' requires manual review (template rows=%s orphan rows=%s).",
            media_id,
            len(template_rows),
            len(orphan_rows),
        )


# noinspection SqlResolve
def _cleanup_legacy_shopify_address_ids(env: api.Environment) -> None:
    existing_columns = _filter_existing_columns(env.cr, "res_partner", ["shopify_address_id", "type"])
    if "shopify_address_id" not in existing_columns:
        return
    if "type" not in existing_columns:
        _logger.warning("Skipping Shopify address legacy cleanup: res_partner.type column missing.")
        return

    system = env["external.system"].sudo().search([("code", "=", "shopify")], limit=1)
    if not system:
        return

    env.cr.execute(
        """
        SELECT id, shopify_address_id, type
          FROM res_partner
         WHERE shopify_address_id IS NOT NULL
           AND shopify_address_id != ''
        """
    )
    legacy_rows = env.cr.fetchall()
    if not legacy_rows:
        env.cr.execute("ALTER TABLE res_partner DROP COLUMN IF EXISTS shopify_address_id")
        _logger.info("Dropped legacy res_partner.shopify_address_id (no values remaining).")
        return

    env.cr.execute(
        """
        SELECT res_id, resource, external_id
          FROM external_id
         WHERE system_id = %s
           AND res_model = 'res.partner'
           AND resource IN %s
        """,
        (system.id, (ADDRESS_RESOURCE_DEFAULT, ADDRESS_RESOURCE_INVOICE, ADDRESS_RESOURCE_DELIVERY)),
    )
    address_map: dict[tuple[str, str], set[int]] = {}
    for res_id, resource, external_id in env.cr.fetchall():
        if not resource or not external_id:
            continue
        key = (resource, external_id)
        address_map.setdefault(key, set()).add(res_id)

    duplicate_keys = [key for key, res_ids in address_map.items() if len(res_ids) > 1]
    if duplicate_keys:
        sample = list(sorted(duplicate_keys))[:10]
        _logger.warning(
            "Preserving legacy res_partner.shopify_address_id (duplicate Shopify address IDs detected: %s%s).",
            sample,
            "..." if len(duplicate_keys) > len(sample) else "",
        )
        return

    required_address_keys: set[tuple[str, str]] = set()
    for partner_id, raw_value, partner_type in legacy_rows:
        normalized_external_id, role = _parse_shopify_address_value(raw_value)
        if not normalized_external_id:
            _logger.warning(
                "Preserving legacy res_partner.shopify_address_id (invalid value '%s' on partner %s).",
                raw_value,
                partner_id,
            )
            return
        resource = _shopify_address_resource_for_partner(partner_type, role)
        key = (resource, normalized_external_id)
        required_address_keys.add(key)
        mapped_ids = address_map.get(key)
        if not mapped_ids:
            _logger.warning(
                "Preserving legacy res_partner.shopify_address_id (missing Shopify address ID %s for partner %s).",
                key,
                partner_id,
            )
            return
        if mapped_ids != {partner_id}:
            _logger.warning(
                "Preserving legacy res_partner.shopify_address_id (Shopify address ID %s mapped to %s instead of %s).",
                key,
                sorted(mapped_ids),
                partner_id,
            )
            return

    if not required_address_keys:
        return

    env.cr.execute(
        """
        UPDATE res_partner
           SET shopify_address_id = NULL
         WHERE shopify_address_id IS NOT NULL
           AND shopify_address_id != ''
        """
    )
    env.cr.execute("ALTER TABLE res_partner DROP COLUMN IF EXISTS shopify_address_id")
    _logger.info(
        "Dropped legacy res_partner.shopify_address_id after verifying %s Shopify address IDs.",
        len(required_address_keys),
    )


# noinspection SqlResolve
def _deduplicate_ebay_usernames(env: api.Environment) -> None:
    if not _filter_existing_columns(env.cr, "res_partner", ["ebay_username"]):
        return

    env.cr.execute(
        """
        SELECT ebay_username
          FROM res_partner
         WHERE ebay_username IS NOT NULL
           AND ebay_username != ''
         GROUP BY ebay_username
        HAVING COUNT(*) > 1
        """
    )
    duplicate_usernames = [row[0] for row in env.cr.fetchall()]
    if not duplicate_usernames:
        return

    partner_model = env["res.partner"].sudo()
    system = env["external.system"].sudo().search([("code", "=", "ebay")], limit=1)

    for username in duplicate_usernames:
        env.cr.execute(
            """
            SELECT id, active, customer_rank, supplier_rank, email, phone, write_date, create_date
              FROM res_partner
             WHERE ebay_username = %s
            """,
            (username,),
        )
        partner_rows = env.cr.fetchall()
        partner_ids = [row[0] for row in partner_rows]
        if len(partner_ids) < 2:
            continue

        order_counts = _partner_activity_counts(env, "sale_order", partner_ids)
        invoice_counts = _partner_activity_counts(
            env,
            "account_move",
            partner_ids,
            where="move_type IN ('out_invoice', 'out_refund')",
        )

        canonical_id = _select_canonical_partner(partner_rows, order_counts, invoice_counts)
        secondary_ids = [partner_id for partner_id in partner_ids if partner_id != canonical_id]
        if not secondary_ids:
            continue

        canonical = partner_model.browse(canonical_id).exists()
        if not canonical:
            continue
        ancestor_ids = _partner_ancestor_ids(env, canonical.id)
        if ancestor_ids:
            ancestors_in_secondaries = ancestor_ids.intersection(set(secondary_ids))
            if ancestors_in_secondaries:
                canonical.write({"parent_id": False})
                _logger.warning(
                    "Detached canonical partner %s from parent chain to avoid eBay merge cycle (ancestors: %s).",
                    canonical_id,
                    sorted(ancestors_in_secondaries),
                )

        secondaries = partner_model.browse(secondary_ids).exists()
        if secondaries:
            secondaries.write({"parent_id": canonical.id, "type": "contact"})

        env.cr.execute(
            """
            UPDATE res_partner
               SET ebay_username = NULL
             WHERE id = ANY(%s)
            """,
            (secondary_ids,),
        )
        _logger.info(
            "Merged duplicate eBay username '%s' into partner %s; cleared %s",
            username,
            canonical_id,
            secondary_ids,
        )

        if system:
            env.cr.execute(
                """
                UPDATE external_id
                   SET res_model = 'res.partner',
                       res_id = %s,
                       active = TRUE
                 WHERE system_id = %s
                   AND resource = 'profile'
                   AND external_id = %s
                """,
                (canonical_id, system.id, username),
            )


# noinspection SqlResolve
def _deduplicate_shopify_address_ids(env: api.Environment) -> None:
    existing_columns = _filter_existing_columns(env.cr, "res_partner", ["shopify_address_id", "type"])
    if "shopify_address_id" not in existing_columns:
        return
    if "type" not in existing_columns:
        _logger.warning("Skipping Shopify address dedupe: res_partner.type column missing.")
        return

    system = env["external.system"].sudo().search([("code", "=", "shopify")], limit=1)
    if not system:
        return

    env.cr.execute(
        """
        SELECT id, shopify_address_id, type
          FROM res_partner
         WHERE shopify_address_id IS NOT NULL
           AND shopify_address_id != ''
        """
    )
    legacy_rows = env.cr.fetchall()
    if not legacy_rows:
        return

    address_groups: dict[tuple[str, str], list[int]] = {}
    for partner_id, raw_value, partner_type in legacy_rows:
        normalized_external_id, role = _parse_shopify_address_value(raw_value)
        if not normalized_external_id:
            continue
        resource = _shopify_address_resource_for_partner(partner_type, role)
        address_groups.setdefault((resource, normalized_external_id), []).append(partner_id)

    duplicate_groups = {key: ids for key, ids in address_groups.items() if len(ids) > 1}
    if not duplicate_groups:
        return

    external_id_model = env["external.id"].sudo().with_context(active_test=False)
    partner_model = env["res.partner"].sudo()

    for (resource, external_id_value), partner_ids in duplicate_groups.items():
        partner_model.flush_model(["active", "customer_rank", "supplier_rank", "email", "phone", "write_date", "create_date"])
        env.cr.execute(
            """
            SELECT id, active, customer_rank, supplier_rank, email, phone, write_date, create_date
              FROM res_partner
             WHERE id = ANY(%s)
            """,
            (partner_ids,),
        )
        partner_rows = env.cr.fetchall()
        if len(partner_rows) < 2:
            continue

        usage_counts = _partner_address_usage_counts(env, partner_ids)
        canonical_id = _select_canonical_address_partner(partner_rows, usage_counts)
        secondary_ids = [partner_id for partner_id in partner_ids if partner_id != canonical_id]

        external_id_record = external_id_model.search(
            [
                ("system_id", "=", system.id),
                ("resource", "=", resource),
                ("external_id", "=", external_id_value),
            ],
            limit=1,
        )
        partner_record = external_id_model.search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", canonical_id),
                ("system_id", "=", system.id),
                ("resource", "=", resource),
            ],
            limit=1,
        )
        if external_id_record and partner_record and external_id_record.id != partner_record.id:
            if partner_record.external_id == external_id_value:
                external_id_record.unlink()
            else:
                partner_record.unlink()
                external_id_record.write({"res_model": "res.partner", "res_id": canonical_id, "active": True})
        elif external_id_record:
            if external_id_record.res_id != canonical_id or not external_id_record.active:
                external_id_record.write({"res_model": "res.partner", "res_id": canonical_id, "active": True})
        elif partner_record:
            partner_record.write({"external_id": external_id_value, "active": True})
        else:
            external_id_model.create(
                {
                    "res_model": "res.partner",
                    "res_id": canonical_id,
                    "system_id": system.id,
                    "resource": resource,
                    "external_id": external_id_value,
                    "active": True,
                }
            )

        if secondary_ids:
            env.cr.execute(
                """
                UPDATE res_partner
                   SET shopify_address_id = NULL
                 WHERE id = ANY(%s)
                """,
                (secondary_ids,),
            )
            _logger.info(
                "Cleared duplicate Shopify address id '%s' for partners %s (canonical %s).",
                external_id_value,
                secondary_ids,
                canonical_id,
            )


def _partner_address_usage_counts(env: api.Environment, partner_ids: list[int]) -> dict[int, int]:
    if not partner_ids:
        return {}
    counts: dict[int, int] = {partner_id: 0 for partner_id in partner_ids}

    def _accumulate(table_name: str, column_name: str, where: str | None = None) -> None:
        if not _filter_existing_columns(env.cr, table_name, [column_name]):
            return
        where_clause = f"AND {where}" if where else ""
        env.cr.execute(
            f"""
            SELECT {column_name}, COUNT(*)
              FROM {table_name}
             WHERE {column_name} = ANY(%s)
               {where_clause}
             GROUP BY {column_name}
            """,
            (partner_ids,),
        )
        for partner_id, count in env.cr.fetchall():
            if partner_id in counts:
                counts[partner_id] += count

    _accumulate("sale_order", "partner_shipping_id")
    _accumulate("sale_order", "partner_invoice_id")
    _accumulate(
        "account_move",
        "partner_shipping_id",
        where="move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')",
    )
    _accumulate(
        "account_move",
        "partner_invoice_id",
        where="move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')",
    )
    return counts


def _select_canonical_address_partner(
    partner_rows: list[tuple],
    usage_counts: dict[int, int],
) -> int:
    def score(row: tuple) -> tuple:
        (
            partner_id,
            active,
            customer_rank,
            supplier_rank,
            email,
            phone,
            write_date,
            create_date,
        ) = row
        return (
            usage_counts.get(partner_id, 0),
            int(active or 0),
            int(customer_rank or 0),
            int(supplier_rank or 0),
            1 if email else 0,
            1 if phone else 0,
            write_date or create_date or datetime.min,
            partner_id,
        )

    return max(partner_rows, key=score)[0]


def _partner_activity_counts(
    env: api.Environment,
    table_name: str,
    partner_ids: list[int],
    *,
    where: str | None = None,
) -> dict[int, int]:
    if not partner_ids:
        return {}
    env.cr.execute("SELECT to_regclass(%s)", (table_name,))
    if env.cr.fetchone()[0] is None:
        return {}
    where_clause = f"AND {where}" if where else ""
    env.cr.execute(
        f"""
        SELECT partner_id, COUNT(*)
          FROM {table_name}
         WHERE partner_id = ANY(%s)
           {where_clause}
         GROUP BY partner_id
        """,
        (partner_ids,),
    )
    return {partner_id: count for partner_id, count in env.cr.fetchall()}


def _select_canonical_partner(
    partner_rows: list[tuple],
    order_counts: dict[int, int],
    invoice_counts: dict[int, int],
) -> int:
    def score(row: tuple) -> tuple:
        (
            partner_id,
            active,
            customer_rank,
            supplier_rank,
            email,
            phone,
            write_date,
            create_date,
        ) = row
        return (
            order_counts.get(partner_id, 0),
            invoice_counts.get(partner_id, 0),
            int(customer_rank or 0),
            int(supplier_rank or 0),
            1 if email else 0,
            1 if phone else 0,
            1 if active else 0,
            write_date or create_date or datetime.min,
            partner_id,
        )

    return max(partner_rows, key=score)[0]


# noinspection SqlResolve
def _partner_ancestor_ids(env: api.Environment, partner_id: int) -> set[int]:
    if not _filter_existing_columns(env.cr, "res_partner", ["parent_path"]):
        return set()
    env.cr.execute("SELECT parent_path FROM res_partner WHERE id = %s", (partner_id,))
    row = env.cr.fetchone()
    if not row or not row[0]:
        return set()
    path = row[0]
    return {int(part) for part in path.split("/") if part}


# noinspection SqlResolve
def _migrate_shopify_address_ids(env: api.Environment) -> set[str]:
    system = env["external.system"].sudo().search([("code", "=", "shopify")], limit=1)
    if not system:
        return set()

    existing_columns = _filter_existing_columns(env.cr, "res_partner", ["shopify_address_id", "type"])
    if "shopify_address_id" not in existing_columns:
        return set()

    drop_candidates: set[str] = {"shopify_address_id"}

    existing_keys, existing_external_ids = _existing_external_id_maps(
        env,
        system_id=system.id,
        model_name="res.partner",
        resources={
            ADDRESS_RESOURCE_INVOICE,
            ADDRESS_RESOURCE_DELIVERY,
            ADDRESS_RESOURCE_DEFAULT,
        },
    )

    env.cr.execute(
        """
        SELECT id, shopify_address_id, type
          FROM res_partner
         WHERE shopify_address_id IS NOT NULL
           AND shopify_address_id != ''
        """
    )
    rows = env.cr.fetchall()
    if not rows:
        return drop_candidates

    external_id_values: list["odoo.values.external_id"] = []
    ExternalId = env["external.id"].sudo()

    for partner_id, raw_value, partner_type in rows:
        normalized_external_id, role = _parse_shopify_address_value(raw_value)
        if not normalized_external_id:
            _logger.warning(
                "Skipping Shopify address id '%s' for res.partner %s: invalid format",
                raw_value,
                partner_id,
            )
            drop_candidates.discard("shopify_address_id")
            continue

        resource = _shopify_address_resource_for_partner(partner_type, role)
        key = (partner_id, resource)
        existing_record = existing_keys.get(key)
        if existing_record:
            existing_record_id = _coerce_record_id(existing_record.get("id"))
            if existing_record_id is None:
                if existing_record["external_id"] != normalized_external_id:
                    _logger.warning(
                        "Skipping conflicting Shopify address id '%s' for res.partner %s: already staged as '%s'",
                        normalized_external_id,
                        partner_id,
                        existing_record["external_id"],
                    )
                    drop_candidates.discard("shopify_address_id")
                continue

            existing_res_id = existing_external_ids.get((resource, normalized_external_id))
            if existing_res_id and existing_res_id != partner_id:
                _logger.warning(
                    "Skipping duplicate Shopify address id '%s' for res.partner %s: already used by %s",
                    normalized_external_id,
                    partner_id,
                    existing_res_id,
                )
                drop_candidates.discard("shopify_address_id")
                continue

            _apply_external_id_update(
                ExternalId,
                existing_record,
                existing_record_id,
                normalized_external_id,
                resource=resource,
                owner_id=partner_id,
                existing_external_ids=existing_external_ids,
            )
            continue

        existing_res_id = existing_external_ids.get((resource, normalized_external_id))
        if existing_res_id and existing_res_id != partner_id:
            _logger.warning(
                "Skipping duplicate Shopify address id '%s' for res.partner %s: already used by %s",
                normalized_external_id,
                partner_id,
                existing_res_id,
            )
            drop_candidates.discard("shopify_address_id")
            continue

        external_id_values.append(
            {
                "res_model": "res.partner",
                "res_id": partner_id,
                "system_id": system.id,
                "resource": resource,
                "external_id": normalized_external_id,
                "active": True,
            }
        )
        existing_keys[key] = {"id": None, "external_id": normalized_external_id, "active": True}
        existing_external_ids[(resource, normalized_external_id)] = partner_id

    if external_id_values:
        created = ExternalId.create(external_id_values)
        for record in created:
            key = (record.res_id, record.resource)
            existing_keys[key] = {
                "id": record.id,
                "external_id": record.external_id,
                "active": record.active,
            }

    return drop_candidates


def _shopify_address_resource_for_partner(partner_type: str | None, role: str | None) -> str:
    if role == "invoice":
        return ADDRESS_RESOURCE_INVOICE
    if role == "delivery":
        return ADDRESS_RESOURCE_DELIVERY
    if partner_type == "delivery":
        return ADDRESS_RESOURCE_DELIVERY
    return ADDRESS_RESOURCE_INVOICE


def _parse_shopify_address_value(raw_value: str) -> tuple[str, str | None]:
    value = (raw_value or "").strip()
    if not value:
        return "", None
    lowered = value.lower()
    role = None
    if ":invoice" in lowered:
        role = "invoice"
    elif ":delivery" in lowered:
        role = "delivery"
    normalized_external_id = _normalize_shopify_external_id(value) or ""
    return normalized_external_id, role


def _ensure_delivery_service_map_xmlids(cr: Cursor) -> None:
    cr.execute("SELECT to_regclass('delivery_carrier_service_map')")
    table_name = cr.fetchone()
    if not table_name or table_name[0] is None:
        return

    mappings = [
        ("map_shopify_via_standard", "shopify", "via standard shipping"),
        ("map_shopify_shipping", "shopify", "shipping"),
        ("map_shopify_standard", "shopify", "standard shipping"),
        ("map_shopify_20_shipping", "shopify", "20 shipping"),
        ("map_shopify_ups_ground", "shopify", "ups ground"),
        ("map_shopify_ups_ground_crate", "shopify", "ups ground crate"),
        ("map_shopify_free_ups_ground", "shopify", "free ups ground"),
        ("map_shopify_ups_2day", "shopify", "ups 2nd day air"),
        ("map_shopify_ups_3day", "shopify", "ups 3 day select"),
        ("map_shopify_ups_nextday", "shopify", "ups next day air"),
        ("map_shopify_ups_nextday_saver", "shopify", "ups next day air saver"),
        ("map_shopify_ups_standard", "shopify", "ups standard"),
        ("map_shopify_ups_worldwide_expedited", "shopify", "ups worldwide expedited"),
        ("map_shopify_ups_worldwide_express", "shopify", "ups worldwide express"),
        ("map_shopify_ups_worldwide_saver", "shopify", "ups worldwide saver"),
        ("map_shopify_usps_ground", "shopify", "usps ground advantage"),
        ("map_shopify_usps_parcel", "shopify", "usps parcel select ground"),
        ("map_shopify_usps_priority", "shopify", "usps priority mail"),
        ("map_shopify_usps_priority_gsp", "shopify", "usps priority mail ebay gsp"),
        ("map_shopify_usps_priority_intl", "shopify", "usps priority mail international"),
        ("map_shopify_usps_first_class", "shopify", "usps first class package"),
        ("map_shopify_usps_first_class_intl", "shopify", "usps first class package international"),
        ("map_shopify_flat_freight", "shopify", "flat rate freight"),
        ("map_shopify_freight", "shopify", "freight"),
        ("map_shopify_freight_shipping", "shopify", "freight shipping"),
        ("map_shopify_freight_shipment", "shopify", "freight shipment"),
        ("map_shopify_freight_commercial", "shopify", "freight commercial address"),
        ("map_shopify_freight_commercial_hub", "shopify", "freight commercial address or local freight hub"),
        ("map_shopify_freight_southeastern", "shopify", "freight via southeastern"),
        ("map_shopify_freight_southeastern_hub", "shopify", "freight via southeastern to local hub"),
        ("map_shopify_ebay_gsp", "shopify", "standard shipping ebay gsp"),
        ("map_shopify_free", "shopify", "free"),
        ("map_shopify_free_shipping", "shopify", "free shipping"),
        ("map_shopify_free_shipping_lowercase", "shopify", "free shipping to pattrick"),
        ("map_shopify_free_dropoff", "shopify", "free dropoff"),
        ("map_shopify_local_pickup", "shopify", "local pickup"),
        ("map_shopify_warehouse", "shopify", "warehouse"),
        ("map_shopify_in_store", "shopify", "in store pickup"),
        ("map_shopify_in_store_appointment", "shopify", "in store pickup must schedule appointment"),
        ("map_shopify_customer_arrange", "shopify", "customer arranged shipping"),
        ("map_shopify_customer_to_arrange", "shopify", "customer to arrange shipping"),
        ("map_shopify_buyer_arrange", "shopify", "buyer to arrange shipping"),
        ("map_shopify_buyer_provide_label", "shopify", "buyer to provide label for shipment"),
        ("map_shopify_buyer_dhl_label", "shopify", "buyer to prove dhl label"),
    ]

    for xml_id, platform, normalized_name in mappings:
        cr.execute(
            """
            SELECT 1
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
             LIMIT 1
            """,
            ("shopify_sync", xml_id),
        )
        if cr.fetchone():
            continue

        cr.execute(
            """
            SELECT id
              FROM delivery_carrier_service_map
             WHERE platform = %s
               AND platform_service_normalized_name = %s
             LIMIT 1
            """,
            (platform, normalized_name),
        )
        record = cr.fetchone()
        if not record:
            continue

        cr.execute(
            """
            INSERT INTO ir_model_data
                (module, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s, %s, true, %s, NOW(), %s, NOW())
            """,
            ("shopify_sync", xml_id, "delivery.carrier.service.map", record[0], SUPERUSER_ID, SUPERUSER_ID),
        )


def _deduplicate_delivery_default_codes(cr: Cursor) -> None:
    cr.execute("SELECT to_regclass('product_template')")
    template_table = cr.fetchone()
    if not template_table or template_table[0] is None:
        return

    cr.execute("SELECT to_regclass('product_product')")
    product_table = cr.fetchone()
    if not product_table or product_table[0] is None:
        return

    mappings = [
        ("product_delivery_ups_ground", "SHIP_UPS_GND"),
        ("product_delivery_ups_2day", "SHIP_UPS_2DA"),
        ("product_delivery_ups_3day", "SHIP_UPS_3DS"),
        ("product_delivery_ups_nextday", "SHIP_UPS_NDA"),
        ("product_delivery_ups_nextday_saver", "SHIP_UPS_NDS"),
        ("product_delivery_ups_standard", "SHIP_UPS_STD"),
        ("product_delivery_ups_worldwide_expedited", "SHIP_UPS_WWE"),
        ("product_delivery_ups_worldwide_express", "SHIP_UPS_WWX"),
        ("product_delivery_ups_worldwide_saver", "SHIP_UPS_WWS"),
        ("product_delivery_usps_ground", "SHIP_USPS_GA"),
        ("product_delivery_usps_parcel", "SHIP_USPS_PSG"),
        ("product_delivery_usps_priority", "SHIP_USPS_PM"),
        ("product_delivery_usps_priority_intl", "SHIP_USPS_PMI"),
        ("product_delivery_usps_first_class", "SHIP_USPS_FC"),
        ("product_delivery_usps_first_class_intl", "SHIP_USPS_FCI"),
        ("product_delivery_freight_flat", "SHIP_FRT_FLAT"),
        ("product_delivery_freight_standard", "SHIP_FRT_STD"),
        ("product_delivery_freight_commercial", "SHIP_FRT_COM"),
        ("product_delivery_freight_southeastern", "SHIP_FRT_SE"),
        ("product_delivery_ebay_gsp", "SHIP_EBAY_GSP"),
        ("product_delivery_warehouse", "SHIP_WAREHOUSE"),
        ("product_delivery_standard", "SHIP_STD"),
        ("product_delivery_free", "SHIP_FREE"),
        ("product_delivery_pickup_store", "SHIP_PICKUP_S"),
        ("product_delivery_pickup_local", "SHIP_PICKUP_L"),
        ("product_delivery_customer_arrange", "SHIP_CUST_ARR"),
    ]

    for xml_id, default_code in mappings:
        cr.execute(
            """
            SELECT res_id
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
               AND model = %s
             LIMIT 1
            """,
            ("shopify_sync", xml_id, "product.product"),
        )
        record = cr.fetchone()
        product_id = record[0] if record else None

        template_id = None
        if product_id:
            cr.execute(
                """
                SELECT product_tmpl_id
                  FROM product_product
                 WHERE id = %s
                 LIMIT 1
                """,
                (product_id,),
            )
            template_record = cr.fetchone()
            template_id = template_record[0] if template_record else None

        if not template_id:
            # noinspection SqlResolve
            # False positive: Odoo tables are not available in the IDE SQL schema.
            cr.execute(
                """
                SELECT product_product.id, product_template.id
                  FROM product_template
                  JOIN product_product
                    ON product_product.product_tmpl_id = product_template.id
                 WHERE product_template.default_code = %s
                 ORDER BY product_product.id
                 LIMIT 1
                """,
                (default_code,),
            )
            record = cr.fetchone()
            if not record:
                continue
            product_id, template_id = record
            cr.execute(
                """
                INSERT INTO ir_model_data
                    (module, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date)
                VALUES
                    (%s, %s, %s, %s, true, %s, NOW(), %s, NOW())
                """,
                ("shopify_sync", xml_id, "product.product", product_id, SUPERUSER_ID, SUPERUSER_ID),
            )

        cr.execute(
            """
            UPDATE product_template
               SET default_code = NULL
             WHERE default_code = %s
               AND id != %s
            """,
            (default_code, template_id),
        )


def _migrate_template_shopify_product_ids(env: api.Environment) -> dict[str, set[str]]:
    system = env["external.system"].sudo().search([("code", "=", "shopify")], limit=1)
    if not system:
        _logger.warning("External system 'shopify' not found; skipping product.template Shopify ID migration")
        return {}

    template_has_shopify_id = "shopify_product_id" in _filter_existing_columns(
        env.cr,
        "product_template",
        ["shopify_product_id"],
    )
    product_has_shopify_id = "shopify_product_id" in _filter_existing_columns(
        env.cr,
        "product_product",
        ["shopify_product_id"],
    )
    if not template_has_shopify_id and not product_has_shopify_id:
        return {}

    drop_candidates_by_table: dict[str, set[str]] = {}
    if template_has_shopify_id:
        drop_candidates_by_table.setdefault("product_template", set()).add("shopify_product_id")
    if product_has_shopify_id:
        drop_candidates_by_table.setdefault("product_product", set()).add("shopify_product_id")

    existing_keys, existing_external_ids = _existing_external_id_maps(
        env,
        system_id=system.id,
        model_name="product.product",
        resources={"product"},
    )
    if template_has_shopify_id:
        if product_has_shopify_id:
            # noinspection SqlResolve
            # False positive: Odoo columns are not available in the IDE SQL schema.
            env.cr.execute(
                """
                SELECT MIN(pp.id) AS variant_id,
                       COALESCE(pt.shopify_product_id, MAX(pp.shopify_product_id)) AS shopify_product_id
                  FROM product_template pt
                  JOIN product_product pp ON pp.product_tmpl_id = pt.id
                 WHERE (pt.shopify_product_id IS NOT NULL AND pt.shopify_product_id != '')
                    OR (pp.shopify_product_id IS NOT NULL AND pp.shopify_product_id != '')
                 GROUP BY pt.id, pt.shopify_product_id
                """,
            )
        else:
            # noinspection SqlResolve
            # False positive: Odoo columns are not available in the IDE SQL schema.
            env.cr.execute(
                """
                SELECT MIN(pp.id) AS variant_id,
                       pt.shopify_product_id AS shopify_product_id
                  FROM product_template pt
                  JOIN product_product pp ON pp.product_tmpl_id = pt.id
                 WHERE pt.shopify_product_id IS NOT NULL
                   AND pt.shopify_product_id != ''
                 GROUP BY pt.id, pt.shopify_product_id
                """,
            )
    else:
        # noinspection SqlResolve
        # False positive: Odoo columns are not available in the IDE SQL schema.
        env.cr.execute(
            """
            SELECT MIN(pp.id) AS variant_id,
                   MAX(pp.shopify_product_id) AS shopify_product_id
              FROM product_product pp
             WHERE pp.shopify_product_id IS NOT NULL
               AND pp.shopify_product_id != ''
             GROUP BY pp.product_tmpl_id
            """,
        )
    rows = env.cr.fetchall()
    if not rows:
        return drop_candidates_by_table

    external_id_values: list["odoo.values.external_id"] = []
    ExternalId = env["external.id"].sudo()
    can_drop_legacy_columns = True

    for variant_id, raw_value in rows:
        if not variant_id:
            continue
        sanitized = (raw_value if isinstance(raw_value, str) else str(raw_value)).strip()
        if not sanitized:
            continue
        normalized_external_id = _normalize_shopify_external_id(sanitized)
        if not normalized_external_id:
            _logger.warning(
                "Skipping Shopify product id '%s' for product.product %s: invalid format",
                sanitized,
                variant_id,
            )
            can_drop_legacy_columns = False
            continue

        key = (variant_id, "product")
        existing_record = existing_keys.get(key)
        if existing_record:
            existing_record_id = _coerce_record_id(existing_record.get("id"))
            if existing_record_id is None:
                continue
            if not existing_record["active"]:
                existing_res_id = existing_external_ids.get(("product", normalized_external_id))
                if existing_res_id and existing_res_id != variant_id:
                    _logger.warning(
                        "Skipping duplicate Shopify product id '%s' for product.product %s: already used by %s",
                        normalized_external_id,
                        variant_id,
                        existing_res_id,
                    )
                    can_drop_legacy_columns = False
                    continue
                update_vals = {"active": True}
                if existing_record["external_id"] != normalized_external_id:
                    update_vals["external_id"] = normalized_external_id
                ExternalId.browse(existing_record_id).write(update_vals)
                existing_record["active"] = True
                existing_record["external_id"] = normalized_external_id
                existing_external_ids[("product", normalized_external_id)] = variant_id
            continue

        existing_res_id = existing_external_ids.get(("product", normalized_external_id))
        if existing_res_id and existing_res_id != variant_id:
            _logger.warning(
                "Skipping duplicate Shopify product id '%s' for product.product %s: already used by %s",
                normalized_external_id,
                variant_id,
                existing_res_id,
            )
            can_drop_legacy_columns = False
            continue

        external_id_values.append(
            {
                "res_model": "product.product",
                "res_id": variant_id,
                "system_id": system.id,
                "resource": "product",
                "external_id": normalized_external_id,
                "active": True,
            }
        )
        existing_keys[key] = {"id": None, "external_id": normalized_external_id, "active": True}
        existing_external_ids[("product", normalized_external_id)] = variant_id

    if external_id_values:
        created = ExternalId.create(external_id_values)
        for record in created:
            key = (record.res_id, record.resource)
            existing_keys[key] = {
                "id": record.id,
                "external_id": record.external_id,
                "active": record.active,
            }

    if not can_drop_legacy_columns:
        return {}

    return drop_candidates_by_table


def _drop_legacy_marketplace_columns(
    env: api.Environment,
    *,
    drop_shopify: bool,
    drop_ebay: bool,
    drop_candidates_by_table: dict[str, set[str]] | None = None,
) -> None:
    shopify_columns = {
        "shopify_customer_id",
        "shopify_address_id",
        "shopify_product_id",
        "shopify_variant_id",
        "shopify_condition_id",
        "shopify_ebay_category_id",
        "shopify_media_id",
    }
    ebay_columns = {"ebay_username"}
    drop_map = {
        "res_partner": ["shopify_customer_id", "shopify_address_id", "ebay_username"],
        "product_product": [
            "shopify_product_id",
            "shopify_variant_id",
            "shopify_condition_id",
            "shopify_ebay_category_id",
        ],
        "product_image": ["shopify_media_id"],
        "product_template": ["shopify_product_id"],
    }

    for table_name, column_names in drop_map.items():
        allowed_columns = None
        if drop_candidates_by_table is not None:
            allowed_columns = drop_candidates_by_table.get(table_name, set())
            if not allowed_columns:
                continue
        scoped_columns = []
        for column_name in column_names:
            if column_name in shopify_columns and not drop_shopify:
                continue
            if column_name in ebay_columns and not drop_ebay:
                continue
            if allowed_columns is not None and column_name not in allowed_columns:
                continue
            scoped_columns.append(column_name)
        if not scoped_columns:
            continue
        existing_columns = _filter_existing_columns(env.cr, table_name, scoped_columns)
        if not existing_columns:
            continue
        drop_clauses = ", ".join([f"DROP COLUMN IF EXISTS {column}" for column in existing_columns])
        _logger.info("Dropping legacy marketplace columns from %s: %s", table_name, ", ".join(existing_columns))
        env.cr.execute(f"ALTER TABLE {table_name} {drop_clauses}")


def _migrate_external_ids_for_system(
    env: api.Environment,
    *,
    model_name: str,
    table_name: str,
    system_code: str,
    field_resource_map: dict[str, str],
) -> set[str]:
    if not field_resource_map:
        return set()

    system = env["external.system"].sudo().search([("code", "=", system_code)], limit=1)
    if not system:
        _logger.warning("External system '%s' not found; skipping %s migration", system_code, model_name)
        return set()

    existing_columns = _filter_existing_columns(env.cr, table_name, list(field_resource_map.keys()))
    if not existing_columns:
        return set()

    filtered_map = {column: resource for column, resource in field_resource_map.items() if column in existing_columns}
    if not filtered_map:
        return set()

    drop_candidates = set(filtered_map.keys())

    existing_keys, existing_external_ids = _existing_external_id_maps(
        env,
        system_id=system.id,
        model_name=model_name,
        resources=set(filtered_map.values()),
    )
    rows = _fetch_column_values(env.cr, table_name, list(filtered_map.keys()))
    if not rows:
        return drop_candidates

    external_id_values: list["odoo.values.external_id"] = []
    ExternalId = env["external.id"].sudo()

    for row in rows:
        res_id = row[0]
        for column_name, raw_value in zip(filtered_map.keys(), row[1:]):
            if raw_value is None:
                continue
            sanitized = (raw_value if isinstance(raw_value, str) else str(raw_value)).strip()
            if not sanitized:
                continue

            resource = filtered_map[column_name]
            normalized_external_id = sanitized
            if system_code == "shopify":
                normalized_external_id = _normalize_shopify_external_id(sanitized)
                if not normalized_external_id:
                    _logger.warning(
                        "Skipping Shopify external id '%s' for %s (resource %s): invalid format",
                        sanitized,
                        model_name,
                        resource,
                    )
                    drop_candidates.discard(column_name)
                    continue

            key = (res_id, resource)
            existing_record = existing_keys.get(key)
            if existing_record:
                existing_record_id = _coerce_record_id(existing_record.get("id"))
                if existing_record_id is None:
                    if existing_record["external_id"] != normalized_external_id:
                        _logger.warning(
                            "Skipping conflicting external id '%s' for %s (resource %s): already staged as '%s'",
                            normalized_external_id,
                            model_name,
                            resource,
                            existing_record["external_id"],
                        )
                        drop_candidates.discard(column_name)
                    continue

                existing_res_id = existing_external_ids.get((resource, normalized_external_id))
                if existing_res_id and existing_res_id != res_id:
                    _logger.warning(
                        "Skipping duplicate external id '%s' for %s (resource %s): already used by %s",
                        normalized_external_id,
                        model_name,
                        resource,
                        existing_res_id,
                    )
                    drop_candidates.discard(column_name)
                    continue

                _apply_external_id_update(
                    ExternalId,
                    existing_record,
                    existing_record_id,
                    normalized_external_id,
                    resource=resource,
                    owner_id=res_id,
                    existing_external_ids=existing_external_ids,
                )
                continue

            existing_res_id = existing_external_ids.get((resource, normalized_external_id))
            if existing_res_id and existing_res_id != res_id:
                _logger.warning(
                    "Skipping duplicate external id '%s' for %s (resource %s): already used by %s",
                    normalized_external_id,
                    model_name,
                    resource,
                    existing_res_id,
                )
                drop_candidates.discard(column_name)
                continue

            external_id_values.append(
                {
                    "res_model": model_name,
                    "res_id": res_id,
                    "system_id": system.id,
                    "resource": resource,
                    "external_id": normalized_external_id,
                    "active": True,
                }
            )
            existing_keys[key] = {"id": None, "external_id": normalized_external_id, "active": True}
            existing_external_ids[(resource, normalized_external_id)] = res_id

    if external_id_values:
        created = ExternalId.create(external_id_values)
        for record in created:
            key = (record.res_id, record.resource)
            existing_keys[key] = {
                "id": record.id,
                "external_id": record.external_id,
                "active": record.active,
            }

    return drop_candidates


def _apply_external_id_update(
    external_id_model: "odoo.model.external_id",
    existing_record: dict[str, object],
    existing_record_id: int,
    normalized_external_id: str,
    *,
    resource: str,
    owner_id: int,
    existing_external_ids: dict[tuple[str, str], int],
) -> None:
    update_values: dict[str, object] = {}
    if not existing_record["active"]:
        update_values["active"] = True
    if existing_record["external_id"] != normalized_external_id:
        update_values["external_id"] = normalized_external_id

    if not update_values:
        return

    previous_external_id = existing_record["external_id"]
    external_id_model.browse(existing_record_id).write(update_values)
    existing_record["active"] = True
    existing_record["external_id"] = normalized_external_id
    if previous_external_id and previous_external_id != normalized_external_id:
        previous_external_id = previous_external_id if isinstance(previous_external_id, str) else str(previous_external_id)
        previous_key = (resource, previous_external_id)
        if existing_external_ids.get(previous_key) == owner_id:
            existing_external_ids.pop(previous_key, None)
    existing_external_ids[(resource, normalized_external_id)] = owner_id


def _fetch_column_values(cr: Cursor, table_name: str, column_names: list[str]) -> list[tuple]:
    if not column_names:
        return []
    where_clause = " OR ".join([f"{column} IS NOT NULL AND {column} != ''" for column in column_names])
    query = f"SELECT id, {', '.join(column_names)} FROM {table_name} WHERE {where_clause}"
    cr.execute(query)
    return cr.fetchall()


def _existing_external_id_maps(
    env: api.Environment,
    *,
    system_id: int,
    model_name: str,
    resources: set[str],
) -> tuple[dict[tuple[int, str], dict[str, object]], dict[tuple[str, str], int]]:
    if not resources:
        return {}, {}

    cr = env.cr
    cr.execute(
        """
        SELECT id, res_id, resource, external_id, active
          FROM external_id
         WHERE system_id = %s
           AND res_model = %s
           AND resource = ANY(%s)
        """,
        [system_id, model_name, list(resources)],
    )
    existing_keys: dict[tuple[int, str], dict[str, object]] = {}
    existing_external_ids: dict[tuple[str, str], int] = {}
    for record_id, res_id, resource, external_id, active in cr.fetchall():
        existing_keys[(res_id, resource)] = {
            "id": record_id,
            "external_id": external_id,
            "active": bool(active),
        }
        if external_id:
            existing_external_ids[(resource, external_id)] = res_id
    return existing_keys, existing_external_ids


def _coerce_record_id(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


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
    existing = {row[0] for row in cr.fetchall()}
    return [name for name in column_names if name in existing]
