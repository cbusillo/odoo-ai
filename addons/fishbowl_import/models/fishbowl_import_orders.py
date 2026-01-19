import logging
import time
from datetime import datetime

from odoo import models

from ..services.fishbowl_client import FishbowlClient
from . import fishbowl_rows
from .fishbowl_import_constants import (
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    LEGACY_BUCKET_ADHOC,
    LEGACY_BUCKET_DISCOUNT,
    LEGACY_BUCKET_FEE,
    LEGACY_BUCKET_MISC,
    LEGACY_BUCKET_SHIPPING,
    RESOURCE_PURCHASE_ORDER,
    RESOURCE_PURCHASE_ORDER_LINE,
    RESOURCE_SALES_ORDER,
    RESOURCE_SALES_ORDER_LINE,
)

_logger = logging.getLogger(__name__)


class FishbowlImporterOrders(models.Model):
    _inherit = "fishbowl.importer"

    def _import_orders(
        self,
        client: FishbowlClient,
        partner_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
        start_datetime: datetime | None,
    ) -> dict[str, dict[int, int]]:
        sales_status_map = self._load_status_map(client, "sostatus")
        purchase_status_map = self._load_status_map(client, "postatus")

        fishbowl_system = self._get_fishbowl_system()
        product_code_map = self._load_product_code_map()
        part_type_map = self._load_part_type_map(client)

        sales_order_rows: list[fishbowl_rows.OrderRow] = fishbowl_rows.ORDER_ROWS_ADAPTER.validate_python(
            self._fetch_orders(
                client,
                "so",
                "dateIssued",
                start_datetime,
                select_columns="id, num, statusId, customerId, dateIssued, dateCreated, customerPO, note",
            )
        )
        sales_line_batches = self._stream_order_lines(
            client,
            "soitem",
            "so",
            "soId",
            "dateIssued",
            start_datetime,
            select_columns="l.id, l.soId, l.productId, l.productNum, l.description, l.qtyOrdered, l.unitPrice, l.uomId",
        )
        sales_line_total = self._count_order_lines(client, "soitem", "so", "soId", "dateIssued", start_datetime)
        purchase_order_rows: list[fishbowl_rows.OrderRow] = fishbowl_rows.ORDER_ROWS_ADAPTER.validate_python(
            self._fetch_orders(
                client,
                "po",
                "dateIssued",
                start_datetime,
                select_columns="id, num, statusId, vendorId, dateIssued, dateCreated, note",
            )
        )
        purchase_line_batches = self._stream_order_lines(
            client,
            "poitem",
            "po",
            "poId",
            "dateIssued",
            start_datetime,
            select_columns="l.id, l.poId, l.partId, l.partNum, l.description, l.qtyToFulfill, l.unitCost, l.uomId",
        )
        purchase_line_total = self._count_order_lines(client, "poitem", "po", "poId", "dateIssued", start_datetime)

        unit_map = self._load_unit_map()
        sale_order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        sale_line_model = self.env["sale.order.line"].sudo().with_context(IMPORT_CONTEXT)
        purchase_order_model = self.env["purchase.order"].sudo().with_context(IMPORT_CONTEXT)
        purchase_line_model = self.env["purchase.order.line"].sudo().with_context(IMPORT_CONTEXT)

        sales_order_map: dict[int, int] = {}
        sales_line_map: dict[int, int] = {}
        purchase_order_map: dict[int, int] = {}
        purchase_line_map: dict[int, int] = {}
        unresolved_sales_product_ids: set[int] = set()
        unresolved_purchase_part_ids: set[int] = set()

        for row in sales_order_rows:
            fishbowl_id = row.id
            partner_id = partner_maps["customer"].get(row.customerId or 0)
            if not partner_id:
                continue
            order_state = self._map_sales_state(sales_status_map.get(row.statusId or 0, ""))
            values: "odoo.values.sale_order" = {
                "name": str(row.num or f"SO-{fishbowl_id}"),
                "partner_id": partner_id,
                "partner_invoice_id": partner_id,
                "partner_shipping_id": partner_id,
                "date_order": row.dateIssued or row.dateCreated,
                "client_order_ref": row.customerPO or False,
                "note": row.note or False,
                "state": order_state,
            }
            order = sale_order_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_SALES_ORDER,
            )
            sales_order_map[fishbowl_id] = order.id

        missing_sales_count = 0
        missing_sales_samples: list[str] = []
        missing_sales_buckets: dict[str, int] = {}
        sales_line_processed = 0
        sales_line_log_every = 25000
        sales_line_log_threshold = sales_line_log_every
        sales_line_started_at = time.monotonic()
        use_full_prefetch = start_datetime is None
        sales_existing_map: dict[str, int] = {}
        sales_stale_map: dict[str, "odoo.model.external_id"] = {}
        sales_blocked: set[str] = set()
        if use_full_prefetch:
            sales_existing_map, sales_stale_map, sales_blocked = self._prefetch_external_id_records_full(
                fishbowl_system.id,
                RESOURCE_SALES_ORDER_LINE,
                "sale.order.line",
            )

        for sales_line_rows in sales_line_batches:
            sales_line_rows = fishbowl_rows.SALES_ORDER_LINE_ROWS_ADAPTER.validate_python(sales_line_rows)
            external_ids = [str(row.id) for row in sales_line_rows]
            if not use_full_prefetch:
                sales_existing_map, sales_stale_map, sales_blocked = self._prefetch_external_id_records(
                    fishbowl_system.id,
                    RESOURCE_SALES_ORDER_LINE,
                    external_ids,
                    "sale.order.line",
                )
            candidate_product_ids = {row.productId for row in sales_line_rows if row.productId is not None}
            missing_product_ids = {
                product_id
                for product_id in candidate_product_ids
                if product_id not in product_maps["product"] and product_id not in unresolved_sales_product_ids
            }
            if missing_product_ids:
                mapped_product_ids = self._import_missing_products(
                    client,
                    missing_product_ids,
                    part_type_map,
                    unit_map,
                    product_maps,
                    product_code_map,
                )
                unresolved_sales_product_ids.update(missing_product_ids - mapped_product_ids)
            create_values: list["odoo.values.sale_order_line"] = []
            create_external_ids: list[str] = []

            for row in sales_line_rows:
                fishbowl_id = row.id
                external_id_value = str(fishbowl_id)
                if external_id_value in sales_blocked:
                    continue
                order_id = sales_order_map.get(row.soId or 0)
                if not order_id:
                    continue
                product_id = self._resolve_product_from_sales_row(row, product_maps, product_code_map)
                # noinspection DuplicatedCode
                missing_product = False
                if not product_id:
                    missing_product = True
                    bucket = self._legacy_bucket_for_line(
                        str(row.description or ""),
                        float(row.unitPrice or 0),
                    )
                    product_id = self._get_legacy_bucket_product_id(bucket)
                    missing_sales_count += 1
                    missing_sales_buckets[bucket] = missing_sales_buckets.get(bucket, 0) + 1
                    if len(missing_sales_samples) < 20:
                        missing_sales_samples.append(str(row.id))
                unit_id = unit_map.get(row.uomId or 0)
                quantity_ordered = row.qtyOrdered or 0
                unit_price = row.unitPrice or 0
                line_name = str(row.description or "").strip() or False
                if missing_product:
                    line_name = self._build_legacy_line_name(
                        description=str(row.description or ""),
                        reference=str(row.productNum or ""),
                        fallback_product_id=product_id,
                    )
                values: "odoo.values.sale_order_line" = {
                    "order_id": order_id,
                    "product_id": product_id or False,
                    "name": line_name or False,
                    "product_uom_qty": float(quantity_ordered),
                    "price_unit": float(unit_price),
                }
                # noinspection DuplicatedCode
                if unit_id:
                    values["product_uom_id"] = unit_id
                existing_line_id = sales_existing_map.get(external_id_value)
                if existing_line_id:
                    sale_line_model.browse(existing_line_id).write(values)
                    sales_line_map[fishbowl_id] = existing_line_id
                    continue
                create_values.append(values)
                create_external_ids.append(external_id_value)

            if create_values:
                created_lines = sale_line_model.create(create_values)
                external_id_payloads: list["odoo.values.external_id"] = []
                for external_id_value, line in zip(create_external_ids, created_lines, strict=True):
                    sales_line_map[int(external_id_value)] = line.id
                    sales_existing_map[external_id_value] = line.id
                    stale_record = sales_stale_map.pop(external_id_value, None)
                    if stale_record:
                        stale_record.write({"res_model": "sale.order.line", "res_id": line.id, "active": True})
                        continue
                    external_id_payloads.append(
                        {
                            "res_model": "sale.order.line",
                            "res_id": line.id,
                            "system_id": fishbowl_system.id,
                            "resource": RESOURCE_SALES_ORDER_LINE,
                            "external_id": external_id_value,
                            "active": True,
                        }
                    )
                if external_id_payloads:
                    self.env["external.id"].sudo().create(external_id_payloads)
            self._commit_and_clear()
            sales_line_processed += len(sales_line_rows)
            if sales_line_processed >= sales_line_log_threshold:
                elapsed = time.monotonic() - sales_line_started_at
                rate = sales_line_processed / elapsed if elapsed else 0.0
                if sales_line_total:
                    percent = (sales_line_processed / sales_line_total) * 100
                    remaining = max(sales_line_total - sales_line_processed, 0)
                    eta_minutes = (remaining / rate / 60) if rate else 0.0
                    _logger.info(
                        "Fishbowl import: sales lines %s/%s (%.1f%%) at %.0f rows/s, ETA %.1f min",
                        sales_line_processed,
                        sales_line_total,
                        percent,
                        rate,
                        eta_minutes,
                    )
                else:
                    _logger.info(
                        "Fishbowl import: sales lines processed %s in %.2fs",
                        sales_line_processed,
                        elapsed,
                    )
                sales_line_log_threshold += sales_line_log_every

        for row in purchase_order_rows:
            fishbowl_id = row.id
            partner_id = partner_maps["vendor"].get(row.vendorId or 0)
            if not partner_id:
                continue
            order_state = self._map_purchase_state(purchase_status_map.get(row.statusId or 0, ""))
            values: "odoo.values.purchase_order" = {
                "name": str(row.num or f"PO-{fishbowl_id}"),
                "partner_id": partner_id,
                "date_order": row.dateIssued or row.dateCreated,
                "note": row.note or False,
                "state": order_state,
            }
            order = purchase_order_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_PURCHASE_ORDER,
            )
            purchase_order_map[fishbowl_id] = order.id

        missing_purchase_count = 0
        missing_purchase_samples: list[str] = []
        missing_purchase_buckets: dict[str, int] = {}
        purchase_line_processed = 0
        purchase_line_log_every = 5000
        purchase_line_log_threshold = purchase_line_log_every
        purchase_line_started_at = time.monotonic()
        purchase_existing_map: dict[str, int] = {}
        purchase_stale_map: dict[str, "odoo.model.external_id"] = {}
        purchase_blocked: set[str] = set()
        if use_full_prefetch:
            purchase_existing_map, purchase_stale_map, purchase_blocked = self._prefetch_external_id_records_full(
                fishbowl_system.id,
                RESOURCE_PURCHASE_ORDER_LINE,
                "purchase.order.line",
            )

        for purchase_line_rows in purchase_line_batches:
            purchase_line_rows = fishbowl_rows.PURCHASE_ORDER_LINE_ROWS_ADAPTER.validate_python(purchase_line_rows)
            external_ids = [str(row.id) for row in purchase_line_rows]
            if not use_full_prefetch:
                purchase_existing_map, purchase_stale_map, purchase_blocked = self._prefetch_external_id_records(
                    fishbowl_system.id,
                    RESOURCE_PURCHASE_ORDER_LINE,
                    external_ids,
                    "purchase.order.line",
                )
            candidate_part_ids = {row.partId for row in purchase_line_rows if row.partId is not None}
            missing_part_ids = {
                part_id
                for part_id in candidate_part_ids
                if part_id not in product_maps["part"] and part_id not in unresolved_purchase_part_ids
            }
            if missing_part_ids:
                mapped_part_ids = self._import_missing_parts(
                    client,
                    missing_part_ids,
                    part_type_map,
                    unit_map,
                    product_maps,
                    product_code_map,
                )
                unresolved_purchase_part_ids.update(missing_part_ids - mapped_part_ids)
            create_values: list["odoo.values.purchase_order_line"] = []
            create_external_ids: list[str] = []

            # noinspection DuplicatedCode
            for row in purchase_line_rows:
                fishbowl_id = row.id
                external_id_value = str(fishbowl_id)
                if external_id_value in purchase_blocked:
                    continue
                order_id = purchase_order_map.get(row.poId or 0)
                if not order_id:
                    continue
                part_id = row.partId
                product_id = product_maps["part"].get(part_id) if part_id is not None else None
                # noinspection DuplicatedCode
                missing_product = False
                if not product_id:
                    missing_product = True
                    bucket = self._legacy_bucket_for_line(
                        str(row.description or ""),
                        float(row.unitCost or 0),
                    )
                    product_id = self._get_legacy_bucket_product_id(bucket)
                    missing_purchase_count += 1
                    missing_purchase_buckets[bucket] = missing_purchase_buckets.get(bucket, 0) + 1
                    if len(missing_purchase_samples) < 20:
                        missing_purchase_samples.append(str(row.id))
                unit_id = unit_map.get(row.uomId or 0)
                quantity_ordered = row.qtyToFulfill or 0
                unit_cost = row.unitCost or 0
                line_name = str(row.description or "").strip() or False
                if missing_product:
                    line_name = self._build_legacy_line_name(
                        description=str(row.description or ""),
                        reference=str(row.partNum or ""),
                        fallback_product_id=product_id,
                    )
                values: "odoo.values.purchase_order_line" = {
                    "order_id": order_id,
                    "product_id": product_id or False,
                    "name": line_name or False,
                    "product_qty": float(quantity_ordered),
                    "price_unit": float(unit_cost),
                }
                # noinspection DuplicatedCode
                if unit_id:
                    values["product_uom_id"] = unit_id
                existing_line_id = purchase_existing_map.get(external_id_value)
                if existing_line_id:
                    purchase_line_model.browse(existing_line_id).write(values)
                    purchase_line_map[fishbowl_id] = existing_line_id
                    continue
                create_values.append(values)
                create_external_ids.append(external_id_value)

            if create_values:
                created_lines = purchase_line_model.create(create_values)
                external_id_payloads: list["odoo.values.external_id"] = []
                for external_id_value, line in zip(create_external_ids, created_lines, strict=True):
                    purchase_line_map[int(external_id_value)] = line.id
                    purchase_existing_map[external_id_value] = line.id
                    stale_record = purchase_stale_map.pop(external_id_value, None)
                    if stale_record:
                        stale_record.write({"res_model": "purchase.order.line", "res_id": line.id, "active": True})
                        continue
                    external_id_payloads.append(
                        {
                            "res_model": "purchase.order.line",
                            "res_id": line.id,
                            "system_id": fishbowl_system.id,
                            "resource": RESOURCE_PURCHASE_ORDER_LINE,
                            "external_id": external_id_value,
                            "active": True,
                        }
                    )
                if external_id_payloads:
                    self.env["external.id"].sudo().create(external_id_payloads)
            self._commit_and_clear()
            purchase_line_processed += len(purchase_line_rows)
            if purchase_line_processed >= purchase_line_log_threshold:
                elapsed = time.monotonic() - purchase_line_started_at
                rate = purchase_line_processed / elapsed if elapsed else 0.0
                if purchase_line_total:
                    percent = (purchase_line_processed / purchase_line_total) * 100
                    remaining = max(purchase_line_total - purchase_line_processed, 0)
                    eta_minutes = (remaining / rate / 60) if rate else 0.0
                    _logger.info(
                        "Fishbowl import: purchase lines %s/%s (%.1f%%) at %.0f rows/s, ETA %.1f min",
                        purchase_line_processed,
                        purchase_line_total,
                        percent,
                        rate,
                        eta_minutes,
                    )
                else:
                    _logger.info(
                        "Fishbowl import: purchase lines processed %s in %.2fs",
                        purchase_line_processed,
                        elapsed,
                    )
                purchase_line_log_threshold += purchase_line_log_every

        if missing_sales_count:
            _logger.warning(
                "Missing product for %s Fishbowl sales lines; buckets=%s; sample_ids=%s",
                missing_sales_count,
                missing_sales_buckets,
                ", ".join(missing_sales_samples),
            )
        if missing_purchase_count:
            _logger.warning(
                "Missing product for %s Fishbowl purchase lines; buckets=%s; sample_ids=%s",
                missing_purchase_count,
                missing_purchase_buckets,
                ", ".join(missing_purchase_samples),
            )

        return {
            "sales_order": sales_order_map,
            "sales_line": sales_line_map,
            "purchase_order": purchase_order_map,
            "purchase_line": purchase_line_map,
        }

    @staticmethod
    def _load_status_map(client: FishbowlClient, table: str) -> dict[int, str]:
        rows = fishbowl_rows.STATUS_ROWS_ADAPTER.validate_python(client.fetch_all(f"SELECT id, name FROM {table} ORDER BY id"))
        return {row.id: str(row.name or "").strip() for row in rows}

    @staticmethod
    def _map_sales_state(status_name: str) -> str:
        mapping = {
            "estimate": "draft",
            "issued": "sale",
            "in progress": "sale",
            "fulfilled": "sale",
            "closed short": "sale",
            "voided": "cancel",
            "cancelled": "cancel",
            "expired": "cancel",
            "historical": "sale",
        }
        return mapping.get(status_name.lower(), "draft")

    # noinspection DuplicatedCode
    @staticmethod
    def _map_purchase_state(status_name: str) -> str:
        mapping = {
            "bid request": "draft",
            "pending approval": "to approve",
            "issued": "purchase",
            "picking": "purchase",
            "partial": "purchase",
            "picked": "purchase",
            "shipped": "purchase",
            "fulfilled": "purchase",
            "closed short": "purchase",
            "void": "cancel",
            "historical": "purchase",
        }
        return mapping.get(status_name.lower(), "draft")

    # noinspection DuplicatedCode
    def _resolve_product_from_sales_row(
        self,
        row: fishbowl_rows.SalesOrderLineRow,
        product_maps: dict[str, dict[int, int]],
        product_code_map: dict[str, int] | None = None,
    ) -> int | None:
        product_id = row.productId
        if product_id is not None and product_id in product_maps["product"]:
            return product_maps["product"][product_id]
        product_number = str(row.productNum or "").strip()
        if product_number:
            if product_code_map is not None:
                cached_id = product_code_map.get(product_number)
                if cached_id:
                    return cached_id
            product = (
                self.env["product.product"]
                .sudo()
                .with_context(active_test=False)
                .search([("default_code", "=", product_number)], limit=1)
            )
            if product:
                return product.id
        return None

    # noinspection DuplicatedCode
    @staticmethod
    def _legacy_bucket_for_line(description: str, unit_price: float) -> str:
        text = description.strip().lower()
        if unit_price < 0:
            return LEGACY_BUCKET_DISCOUNT
        if any(keyword in text for keyword in ("ship", "freight", "ups", "fedex", "dhl", "usps")):
            return LEGACY_BUCKET_SHIPPING
        if any(keyword in text for keyword in ("fee", "handling", "service charge", "credit card", "cc fee")):
            return LEGACY_BUCKET_FEE
        if any(keyword in text for keyword in ("discount", "coupon", "promo", "rebate", "markdown")):
            return LEGACY_BUCKET_DISCOUNT
        if any(keyword in text for keyword in ("misc", "other", "adjustment")):
            return LEGACY_BUCKET_MISC
        return LEGACY_BUCKET_ADHOC

    def _get_legacy_category(self) -> "odoo.model.product_category":
        category_model = self.env["product.category"].sudo().with_context(IMPORT_CONTEXT)
        category = category_model.search([("name", "=", "Legacy Fishbowl")], limit=1)
        return category or category_model.create({"name": "Legacy Fishbowl"})

    # noinspection DuplicatedCode
    def _get_legacy_bucket_product_id(self, bucket: str) -> int:
        bucket_map = {
            LEGACY_BUCKET_SHIPPING: ("LEGACY-SHIPPING", "Legacy Shipping"),
            LEGACY_BUCKET_FEE: ("LEGACY-FEE", "Legacy Fee"),
            LEGACY_BUCKET_DISCOUNT: ("LEGACY-DISCOUNT", "Legacy Discount"),
            LEGACY_BUCKET_MISC: ("LEGACY-MISC", "Legacy Misc Charge"),
            LEGACY_BUCKET_ADHOC: ("LEGACY-ADHOC", "Legacy Ad-hoc Item"),
        }
        code, name = bucket_map.get(bucket, bucket_map[LEGACY_BUCKET_ADHOC])
        product_model = self.env["product.product"].sudo().with_context(IMPORT_CONTEXT)
        product = product_model.search([("default_code", "=", code)], limit=1)
        if product:
            return product.id
        template_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        values: "odoo.values.product_template" = {
            "name": name,
            "default_code": code,
            "categ_id": self._get_legacy_category().id,
            "sale_ok": False,
            "purchase_ok": False,
            "active": True,
            self._product_type_field(template_model): "service",
        }
        template = template_model.create(values)
        return template.product_variant_id.id

    # noinspection DuplicatedCode
    def _build_legacy_line_name(self, description: str, reference: str, fallback_product_id: int | None) -> str:
        description_value = description.strip()
        reference_value = reference.strip()
        if reference_value and reference_value not in description_value:
            line_name = f"{reference_value} - {description_value}" if description_value else reference_value
        else:
            line_name = description_value
        if not line_name and fallback_product_id:
            product = self.env["product.product"].sudo().browse(fallback_product_id)
            line_name = product.display_name
        return line_name
