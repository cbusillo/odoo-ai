import logging
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any, Protocol

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.transaction_utilities.models.cron_budget_mixin import CronRuntimeBudgetExceeded
from psycopg2 import errors as psycopg2_errors
from pydantic import TypeAdapter

from ..services.fishbowl_client import FishbowlClient, FishbowlConnectionSettings
from . import fishbowl_rows
from .fishbowl_import_constants import (
    EXTERNAL_SYSTEM_APPLICABLE_MODEL_XML_IDS,
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    LEGACY_BUCKET_ADHOC,
    LEGACY_BUCKET_DISCOUNT,
    LEGACY_BUCKET_FEE,
    LEGACY_BUCKET_MISC,
    LEGACY_BUCKET_SHIPPING,
)

_logger = logging.getLogger(__name__)

RowParser = Callable[[list[dict[str, object]]], list[Any]] | TypeAdapter[list[Any]]


class _RowWithId(Protocol):
    id: object


# noinspection SqlResolve
class FishbowlImporter(models.Model):
    _name = "fishbowl.importer"
    _description = "Fishbowl Importer"
    _inherit = ["transaction.cron_budget.mixin"]

    @api.model
    def run_scheduled_import(self) -> None:
        importer = self._with_cron_runtime_budget(job_name="Fishbowl Import")
        importer._run_import(update_last_sync=True)

    @api.model
    def run_full_import(self) -> None:
        self._run_import(update_last_sync=False)

    @api.model
    def _run_import(self, *, update_last_sync: bool, start_datetime: datetime | None = None) -> None:
        fishbowl_settings = self._get_fishbowl_settings()
        sync_started_at = fields.Datetime.now()
        use_last_sync_at = self._use_last_sync_at()
        if start_datetime is None and update_last_sync and use_last_sync_at:
            start_datetime = self._get_last_sync_at()
        max_retries = int(os.environ.get("FISHBOWL_IMPORT_SERIALIZATION_RETRIES", "3"))
        retry_sleep = float(os.environ.get("FISHBOWL_IMPORT_SERIALIZATION_SLEEP", "5"))
        attempt = 0
        while True:
            try:
                fishbowl_system = self._get_fishbowl_system()
                with FishbowlClient(fishbowl_settings) as client:
                    total_started_at = time.monotonic()
                    phase_started_at = time.monotonic()
                    self._import_units_of_measure(client, fishbowl_system, sync_started_at)
                    _logger.info("Fishbowl import: units in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    partner_maps = self._import_partners(client, fishbowl_system, sync_started_at)
                    _logger.info("Fishbowl import: partners in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    product_maps = self._import_products(client, fishbowl_system, sync_started_at)
                    _logger.info("Fishbowl import: products in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    order_maps = self._import_orders(
                        client,
                        partner_maps,
                        product_maps,
                        start_datetime,
                        fishbowl_system,
                        sync_started_at,
                    )
                    _logger.info("Fishbowl import: orders in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_shipments(client, order_maps, start_datetime, fishbowl_system, sync_started_at)
                    _logger.info("Fishbowl import: shipments in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_receipts(
                        client,
                        order_maps,
                        product_maps,
                        start_datetime,
                        fishbowl_system,
                        sync_started_at,
                    )
                    _logger.info("Fishbowl import: receipts in %.2fs", time.monotonic() - phase_started_at)
                    phase_started_at = time.monotonic()
                    self._import_on_hand(client, product_maps)
                    _logger.info("Fishbowl import: on-hand in %.2fs", time.monotonic() - phase_started_at)
                    _logger.info("Fishbowl import: total in %.2fs", time.monotonic() - total_started_at)
                break
            except psycopg2_errors.SerializationFailure as exc:
                attempt += 1
                self.env.cr.rollback()
                self.env.clear()
                if attempt > max_retries:
                    _logger.exception("Fishbowl import failed after %s serialization retries", max_retries)
                    self._record_last_run("failed", str(exc))
                    raise
                sleep_for = retry_sleep * attempt
                _logger.warning(
                    "Fishbowl import serialization failure; retrying %s/%s in %.1fs",
                    attempt,
                    max_retries,
                    sleep_for,
                )
                time.sleep(sleep_for)
                continue
            except CronRuntimeBudgetExceeded as exception:
                message = str(exception)
                _logger.info(message)
                self._record_last_run("partial", message)
                return
            except Exception as exc:
                _logger.exception("Fishbowl import failed")
                self._record_last_run("failed", str(exc))
                raise
        self._record_last_run("success", "")
        if update_last_sync and use_last_sync_at:
            self._set_last_sync_at(sync_started_at)

    def _commit_and_clear(self) -> None:
        self.env.cr.execute("SET LOCAL synchronous_commit TO OFF")
        self.env.cr.commit()
        self.env.clear()
        self._raise_if_cron_runtime_budget_exhausted(job_name="Fishbowl Import")

    def _get_external_id_record(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
    ) -> "odoo.model.external_id":
        return self.env["external.id"].sudo().search(
            [
                ("system_id", "=", system.id),
                ("resource", "=", resource),
                ("external_id", "=", external_id_value),
            ],
            limit=1,
        )

    def _should_process_external_row(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
        updated_at: datetime | None,
    ) -> bool:
        if updated_at is None:
            return True
        external_id_record = self._get_external_id_record(system, external_id_value, resource)
        if not external_id_record or not external_id_record.last_sync:
            return True
        return external_id_record.last_sync < updated_at

    def _mark_external_id_synced(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
        sync_timestamp: datetime,
    ) -> None:
        external_id_record = self._get_external_id_record(system, external_id_value, resource)
        if not external_id_record:
            return
        external_id_record.write({"last_sync": sync_timestamp})

    def _mark_external_ids_synced(
        self,
        system_id: int,
        resource: str,
        external_ids: list[str],
        sync_timestamp: datetime,
    ) -> None:
        if not external_ids:
            return
        unique_ids = sorted(set(external_ids))
        external_id_model = self.env["external.id"].sudo()
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("external_id", "in", unique_ids),
            ]
        )
        if records:
            records.write({"last_sync": sync_timestamp})

    def _create_stock_moves_with_external_ids(
        self,
        move_model: "odoo.model.stock_move",
        *,
        create_values: list["odoo.values.stock_move"],
        create_external_ids: list[str],
        stale_map: dict[str, "odoo.model.external_id"],
        system_id: int,
        resource: str,
    ) -> dict[str, int]:
        if not create_values:
            return {}
        created_moves = move_model.create(create_values)
        external_id_payloads: list["odoo.values.external_id"] = []
        created_map: dict[str, int] = {}
        for external_id_value, move in zip(create_external_ids, created_moves, strict=True):
            created_map[external_id_value] = move.id
            stale_record = stale_map.pop(external_id_value, None)
            if stale_record:
                stale_record.write({"res_model": "stock.move", "res_id": move.id, "active": True})
                continue
            external_id_payloads.append(
                {
                    "res_model": "stock.move",
                    "res_id": move.id,
                    "system_id": system_id,
                    "resource": resource,
                    "external_id": external_id_value,
                    "active": True,
                }
            )
        if external_id_payloads:
            self.env["external.id"].sudo().create(external_id_payloads)
        return created_map

    @staticmethod
    def _init_stock_move_batch() -> tuple[
        list["odoo.values.stock_move"],
        list[str],
        dict[str, "odoo.values.stock_move_line"],
        dict[str, int],
        list[str],
    ]:
        return [], [], {}, {}, []

    def _prepare_stock_move_batch(
        self,
        system_id: int,
        resource: str,
        batch_rows: list[_RowWithId],
    ) -> tuple[
        dict[str, int],
        dict[str, "odoo.model.external_id"],
        set[str],
        list["odoo.values.stock_move"],
        list[str],
        dict[str, "odoo.values.stock_move_line"],
        dict[str, int],
        list[str],
    ]:
        external_ids = [str(row.id) for row in batch_rows]
        existing_map, stale_map, blocked = self._prefetch_external_id_records(
            system_id,
            resource,
            external_ids,
            "stock.move",
        )
        (
            create_values,
            create_external_ids,
            move_line_payloads,
            batch_move_ids,
            processed_external_ids,
        ) = self._init_stock_move_batch()
        return (
            existing_map,
            stale_map,
            blocked,
            create_values,
            create_external_ids,
            move_line_payloads,
            batch_move_ids,
            processed_external_ids,
        )

    @staticmethod
    def _ensure_stock_move_lines(
        move_model: "odoo.model.stock_move",
        move_line_model: "odoo.model.stock_move_line",
        move_ids_by_external_id: dict[str, int],
        move_line_payloads: dict[str, "odoo.values.stock_move_line"],
    ) -> None:
        if not move_ids_by_external_id or not move_line_payloads:
            return
        for external_id_value, move_id in move_ids_by_external_id.items():
            move = move_model.browse(move_id)
            if move.move_line_ids:
                continue
            move_line_values = move_line_payloads.get(external_id_value)
            if not move_line_values:
                continue
            move_line_values["move_id"] = move.id
            move_line_model.create(move_line_values)

    def _get_or_create_by_external_id_with_sync(
        self,
        record_model: "odoo.model.external_id_mixin",
        system: "odoo.model.external_system",
        external_id_value: str,
        values: dict[str, object],
        *,
        resource: str,
        updated_at: datetime | None,
        sync_started_at: datetime,
    ) -> "odoo.model.external_id_mixin":
        if updated_at and not self._should_process_external_row(system, external_id_value, resource, updated_at):
            existing_record = record_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                resource,
            )
            if existing_record:
                return existing_record
        record = record_model.get_or_create_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            external_id_value,
            values,
            resource,
        )
        sync_timestamp = updated_at or sync_started_at
        self._mark_external_id_synced(system, external_id_value, resource, sync_timestamp)
        return record

    def _get_fishbowl_settings(self) -> FishbowlConnectionSettings:
        host = self._get_config_value("fishbowl.host", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__HOST")
        user = self._get_config_value("fishbowl.user", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__USER")
        database = self._get_config_value("fishbowl.db", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__DB")
        password = self._get_config_value("fishbowl.password", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__PASSWORD")
        port_raw = self._get_config_value("fishbowl.port", "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__PORT", required=False)
        port = int(port_raw) if port_raw else 3306
        ssl_verify = self._get_config_bool(
            "fishbowl.ssl_verify",
            "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__SSL_VERIFY",
            default=True,
        )
        if not host or not user or not database or not password:
            raise UserError("Fishbowl connection settings are missing.")
        if not ssl_verify:
            _logger.warning("Fishbowl SSL verification disabled; enable for production.")
        return FishbowlConnectionSettings(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            ssl_verify=ssl_verify,
        )

    # noinspection DuplicatedCode
    def _get_config_value(self, key: str, env_key: str, *, required: bool = True) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if required and not value:
            raise UserError(f"Missing configuration for {key}.")
        return value

    def _get_config_bool(self, key: str, env_key: str, *, default: bool) -> bool:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if not value:
            return default
        return self._to_bool(value)

    def _get_config_int(self, key: str, env_key: str, *, default: int) -> int:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if not value:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _use_last_sync_at(self) -> bool:
        return self._get_config_bool(
            "fishbowl.use_last_sync_at",
            "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__USE_LAST_SYNC_AT",
            default=True,
        )

    def _get_commit_interval(self) -> int:
        return self._get_config_int(
            "fishbowl.commit_interval",
            "ENV_OVERRIDE_CONFIG_PARAM__FISHBOWL__COMMIT_INTERVAL",
            default=50,
        )

    def _get_last_sync_at(self) -> datetime | None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param("fishbowl.last_sync_at")
        if not value:
            return None
        try:
            return fields.Datetime.from_string(value)
        except (TypeError, ValueError):
            return None

    def _set_last_sync_at(self, value: datetime) -> None:
        self.env["ir.config_parameter"].sudo().set_param("fishbowl.last_sync_at", fields.Datetime.to_string(value))

    def _record_last_run(self, status: str, message: str) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("fishbowl.last_run_status", status)
        parameter_model.set_param("fishbowl.last_run_message", message)
        parameter_model.set_param("fishbowl.last_run_at", fields.Datetime.to_string(fields.Datetime.now()))

    @staticmethod
    def _finalize_picking(picking: "odoo.model.stock_picking") -> None:
        target_date = picking.date_done or picking.scheduled_date or fields.Datetime.now()
        try:
            picking.with_context(force_period_date=target_date)._action_done()
        except (AccessError, UserError, ValidationError, ValueError):
            _logger.exception("Failed to finalize picking %s", picking.name)
            return
        updates: "odoo.values.stock_picking" = {}
        if "date_done" in picking._fields:
            updates["date_done"] = target_date
        if updates:
            picking.write(updates)
        move_updates: "odoo.values.stock_move" = {}
        if "date" in picking.move_ids._fields:
            move_updates["date"] = target_date
        if move_updates:
            picking.move_ids.write(move_updates)
        line_updates: "odoo.values.stock_move_line" = {}
        if "date" in picking.move_line_ids._fields:
            line_updates["date"] = target_date
        if line_updates:
            picking.move_line_ids.write(line_updates)

    def _get_fishbowl_system(self) -> "odoo.model.external_system":
        return self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="Fishbowl",
            id_format=r"^\d+$",
            sequence=60,
            active=True,
            applicable_model_xml_ids=EXTERNAL_SYSTEM_APPLICABLE_MODEL_XML_IDS,
        )

    @staticmethod
    def _write_if_changed(
        record: "odoo.model.product_product | odoo.model.product_template | odoo.model.stock_picking",
        values: "odoo.values.product_product | odoo.values.product_template | odoo.values.stock_picking",
    ) -> None:
        changes: "odoo.values.product_product | odoo.values.product_template | odoo.values.stock_picking" = {}
        for field_name, value in values.items():
            if field_name not in record._fields:
                continue
            current_value = record[field_name]
            if isinstance(current_value, models.BaseModel):
                current_value = current_value.id
            if current_value != value:
                changes[field_name] = value
        if changes:
            record.write(changes)

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

    @staticmethod
    def _map_part_type(part_type_name: str) -> str:
        mapping = {
            "service": "service",
            "labor": "service",
            "overhead": "service",
        }
        return mapping.get(part_type_name.lower(), "consu")

    @staticmethod
    def _map_tracking(tracking_flag: object, serialized_flag: object) -> str:
        if FishbowlImporter._to_bool(serialized_flag):
            return "serial"
        if FishbowlImporter._to_bool(tracking_flag):
            return "lot"
        return "none"

    # noinspection DuplicatedCode
    # Duplicated with RepairShopr importer to keep parsing local and avoid cross-addon coupling.
    @staticmethod
    def _to_bool(value: object) -> bool:
        if value in (True, False):
            return bool(value)
        if value is None:
            return False
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw_value = bytes(value)
            if not raw_value:
                return False
            if all(byte in (0, 1) for byte in raw_value):
                return any(byte == 1 for byte in raw_value)
            try:
                decoded = raw_value.decode().strip()
            except UnicodeDecodeError:
                return any(raw_value)
            return FishbowlImporter._to_bool(decoded)
        if isinstance(value, (int, float)):
            return bool(value)
        value_str = str(value).strip().lower()
        return value_str in {"1", "true", "yes", "on", "y", "t"}

    @staticmethod
    def _product_type_field(template_model: "odoo.model.product_template") -> str:
        return "detailed_type" if "detailed_type" in template_model._fields else "type"

    def _load_unit_map(self) -> dict[int, int]:
        unit_map: dict[int, int] = {}
        external_id_model = self.env["external.id"].sudo()
        fishbowl_system = self._get_fishbowl_system()
        unit_records = external_id_model.search(
            [
                ("system_id", "=", fishbowl_system.id),
                ("resource", "=", "uom"),
                ("res_model", "=", "uom.uom"),
            ]
        )
        for record in unit_records:
            unit_map[int(record.external_id)] = record.res_id
        if unit_map:
            return unit_map

        unit_rows = self.env["uom.uom"].sudo().search([])
        for unit in unit_rows:
            unit_map[int(unit.id)] = unit.id
        return unit_map

    def _load_product_code_map(self) -> dict[str, int]:
        product_rows = (
            self.env["product.product"]
            .sudo()
            .with_context(active_test=False)
            .search_read(
                [("default_code", "!=", False)],
                ["id", "default_code"],
            )
        )
        product_map: dict[str, int] = {}
        for row in product_rows:
            default_code = str(row.get("default_code") or "").strip()
            if not default_code:
                continue
            product_map[default_code] = int(row["id"])
        return product_map

    @staticmethod
    def _fetch_orders(
        client: FishbowlClient,
        table: str,
        date_column: str,
        start_datetime: datetime | None,
        *,
        extra_where: str | None = None,
        select_columns: str | None = None,
    ) -> list[dict[str, Any]]:
        columns = select_columns or "*"
        conditions: list[str] = []
        params: list[Any] = []
        if start_datetime is not None:
            conditions.append(f"{date_column} >= %s")
            params.append(start_datetime)
        if extra_where:
            conditions.append(extra_where)
        where_clause = ""
        if conditions:
            where_clause = f" WHERE {' AND '.join(conditions)}"
        query = f"SELECT {columns} FROM {table}{where_clause} ORDER BY id"
        return client.fetch_all(query, params)

    @staticmethod
    def _parse_rows(row_parser: RowParser, rows: list[dict[str, object]]) -> list[Any]:
        if isinstance(row_parser, TypeAdapter):
            return row_parser.validate_python(rows)
        return row_parser(rows)

    @staticmethod
    def _fetch_rows(
        client: FishbowlClient,
        row_parser: RowParser,
        query: str,
        params: list[object] | None = None,
    ) -> list[Any]:
        return FishbowlImporter._parse_rows(row_parser, client.fetch_all(query, params))

    @staticmethod
    def _stream_order_lines(
        client: FishbowlClient,
        line_table: str,
        order_table: str,
        order_foreign_key: str,
        order_date_column: str,
        start_datetime: datetime | None,
        *,
        select_columns: str,
        batch_size: int = 500,
    ) -> Iterator[list[dict[str, Any]]]:
        last_id = 0
        while True:
            conditions: list[str] = ["l.id > %s"]
            params: list[Any] = [last_id]
            if start_datetime is not None:
                conditions.append(f"o.{order_date_column} >= %s")
                params.append(start_datetime)
            where_clause = f" WHERE {' AND '.join(conditions)}"
            query = (
                f"SELECT {select_columns} FROM {line_table} l "
                f"JOIN {order_table} o ON o.id = l.{order_foreign_key}"
                f"{where_clause} ORDER BY l.id LIMIT %s"
            )
            params.append(batch_size)
            rows = client.fetch_all(query, params)
            if not rows:
                break
            yield rows
            last_row_id = rows[-1].get("id") or rows[-1].get("ID")
            last_id = int(last_row_id or last_id)

    @staticmethod
    def _count_order_lines(
        client: FishbowlClient,
        line_table: str,
        order_table: str,
        order_foreign_key: str,
        order_date_column: str,
        start_datetime: datetime | None,
    ) -> int:
        conditions: list[str] = []
        params: list[Any] = []
        if start_datetime is not None:
            conditions.append(f"o.{order_date_column} >= %s")
            params.append(start_datetime)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT COUNT(*) AS total FROM {line_table} l JOIN {order_table} o ON o.id = l.{order_foreign_key}{where_clause}"
        result = client.fetch_all(query, params)
        if not result:
            return 0
        total_value = result[0].get("total") or result[0].get("TOTAL") or 0
        return int(total_value or 0)

    # noinspection DuplicatedCode
    def _prefetch_external_id_records(
        self,
        system_id: int,
        resource: str,
        external_ids: list[str],
        expected_model: str,
    ) -> tuple[dict[str, int], dict[str, "odoo.model.external_id"], set[str]]:
        if not external_ids:
            return {}, {}, set()
        external_id_model = self.env["external.id"].sudo()
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("external_id", "in", external_ids),
            ]
        )
        existing_map: dict[str, int] = {}
        stale_map: dict[str, "odoo.model.external_id"] = {}
        blocked_ids: set[str] = set()
        expected_model_env = self.env[expected_model].sudo()
        for record in records:
            if record.res_model and record.res_model != expected_model:
                blocked_ids.add(record.external_id)
                continue
            if record.res_id:
                existing = expected_model_env.browse(record.res_id).exists()
                if existing:
                    existing_map[record.external_id] = existing.id
                    continue
            stale_map[record.external_id] = record
        return existing_map, stale_map, blocked_ids

    # noinspection DuplicatedCode
    def _prefetch_external_id_records_full(
        self,
        system_id: int,
        resource: str,
        expected_model: str,
    ) -> tuple[dict[str, int], dict[str, "odoo.model.external_id"], set[str]]:
        external_id_model = self.env["external.id"].sudo()
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
            ]
        )
        existing_map: dict[str, int] = {}
        stale_map: dict[str, "odoo.model.external_id"] = {}
        blocked_ids: set[str] = set()
        expected_model_env = self.env[expected_model].sudo()
        for record in records:
            if record.res_model and record.res_model != expected_model:
                blocked_ids.add(record.external_id)
                continue
            if record.res_id:
                existing = expected_model_env.browse(record.res_id).exists()
                if existing:
                    existing_map[record.external_id] = existing.id
                    continue
            stale_map[record.external_id] = record
        return existing_map, stale_map, blocked_ids

    @staticmethod
    def _fetch_rows_by_ids(
        client: FishbowlClient,
        table: str,
        id_column: str,
        record_ids: list[int],
        *,
        select_columns: str | None = None,
        batch_size: int = 500,
        extra_where: str | None = None,
        extra_params: list[Any] | None = None,
        row_parser: RowParser | None = None,
    ) -> list[Any]:
        if not record_ids:
            return []
        columns = select_columns or "*"
        results: list[dict[str, object]] = []
        deduped_ids = sorted(set(record_ids))
        for start_index in range(0, len(deduped_ids), batch_size):
            batch_ids = deduped_ids[start_index : start_index + batch_size]
            placeholders = ", ".join(["%s"] * len(batch_ids))
            query = f"SELECT {columns} FROM {table} WHERE {id_column} IN ({placeholders})"
            params: list[Any] = list(batch_ids)
            if extra_where:
                query = f"{query} AND {extra_where}"
                if extra_params:
                    params.extend(extra_params)
            query = f"{query} ORDER BY id"
            results.extend(client.fetch_all(query, params))
        if row_parser:
            return FishbowlImporter._parse_rows(row_parser, results)
        return results

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
        values = {
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

    @staticmethod
    def _is_stockable_product(product: "odoo.model.product_product") -> bool:
        if "is_storable" in product._fields:
            return bool(product.is_storable)
        type_field = "detailed_type" if "detailed_type" in product._fields else "type"
        return getattr(product, type_field, "") == "product"

    def _resolve_sales_line_for_shipment_row(
        self,
        row: fishbowl_rows.ShipmentLineRow,
        order_maps: dict[str, dict[int, int]],
        sales_line_external_map: dict[int, int] | None = None,
    ) -> "odoo.model.sale_order_line":
        if row.soItemId is None:
            return self.env["sale.order.line"].browse()
        sales_order_item_id = row.soItemId
        sales_order_line_id = order_maps["sales_line"].get(sales_order_item_id)
        if not sales_order_line_id and sales_line_external_map:
            sales_order_line_id = sales_line_external_map.get(sales_order_item_id)
        if not sales_order_line_id:
            return self.env["sale.order.line"].browse()
        return self.env["sale.order.line"].sudo().browse(sales_order_line_id).exists()

    def _resolve_product_from_receipt_row(
        self,
        row: fishbowl_rows.ReceiptItemRow,
        order_maps: dict[str, dict[int, int]],
        product_maps: dict[str, dict[int, int]],
    ) -> int | None:
        purchase_line_id = order_maps["purchase_line"].get(row.poItemId or 0)
        if purchase_line_id:
            return self.env["purchase.order.line"].sudo().browse(purchase_line_id).product_id.id
        if row.partId is not None:
            return product_maps["part"].get(row.partId)
        return None

    def _get_picking_type(self, code: str) -> "odoo.model.stock_picking_type | None":
        picking_type = self.env["stock.picking.type"].sudo().search([("code", "=", code)], limit=1)
        return picking_type if picking_type else None

    def _get_location(self, usage: str) -> "odoo.model.stock_location":
        location = self.env["stock.location"].sudo().search([("usage", "=", usage)], limit=1)
        if not location:
            raise UserError(f"No stock location found for usage '{usage}'.")
        return location
