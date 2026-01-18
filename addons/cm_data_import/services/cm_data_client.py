from __future__ import annotations

import logging
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType

import pymysql

_logger = logging.getLogger(__name__)


SCHOOL_INFORMATION_DATABASE = "school_information"


@dataclass(frozen=True)
class CmDataConnectionSettings:
    host: str
    user: str
    password: str
    port: int = 3306
    database: str | None = None
    use_ssl: bool = False
    ssl_verify: bool = True


@dataclass(frozen=True)
class CmDataAccountName:
    record_id: int
    account_name: str
    ticket_name: str | None
    label_names: str | None
    priority_flag: bool
    on_delivery_schedule: bool
    shipping_enable: bool
    location_drop: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataContact:
    record_id: int
    account_name: str
    sub_name: str | None
    contact_notes: str | None
    sort_order: int | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataDeliveryLog:
    record_id: int
    location_id: int | None
    location_name: str
    status: str
    units: int
    discord_id: int | None
    discord_name: str | None
    notes: str | None
    edit_notes: str | None
    ocr_notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


RawValue = str | int | float | bool | bytes | bytearray | memoryview | datetime | Decimal | None
QueryParameter = str | int | float | bool | bytes | datetime | None
RowData = dict[str, RawValue]


class CmDataClient:
    def __init__(self, settings: CmDataConnectionSettings) -> None:
        self._settings = settings
        self._database = settings.database or SCHOOL_INFORMATION_DATABASE
        self._connection: pymysql.connections.Connection | None = None

    def __enter__(self) -> "CmDataClient":
        self._connection = self._open_connection()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def clear_cache(self) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    def fetch_account_names(self, updated_at: datetime | None) -> list[CmDataAccountName]:
        rows = self._fetch_table_rows(
            "account_names",
            [
                "id",
                "account_name",
                "ticket_name",
                "label_names",
                "priority_flag",
                "on_delivery_schedule",
                "shipping_enable",
                "location_drop",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataAccountName] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="account_names.id")
            account_name = _require_text(row.get("account_name"), field_name="account_names.account_name")
            results.append(
                CmDataAccountName(
                    record_id=record_id,
                    account_name=account_name,
                    ticket_name=_to_text(row.get("ticket_name")),
                    label_names=_to_text(row.get("label_names")),
                    priority_flag=_to_bool(row.get("priority_flag")),
                    on_delivery_schedule=_to_bool(row.get("on_delivery_schedule")),
                    shipping_enable=_to_bool(row.get("shipping_enable")),
                    location_drop=_to_text(row.get("location_drop")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return results

    def fetch_contacts(self, updated_at: datetime | None) -> list[CmDataContact]:
        rows = self._fetch_table_rows(
            "who_to_contact",
            [
                "id",
                "account_name",
                "sub_name",
                "contact_notes",
                "sort_order",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataContact] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="who_to_contact.id")
            account_name = _require_text(row.get("account_name"), field_name="who_to_contact.account_name")
            results.append(
                CmDataContact(
                    record_id=record_id,
                    account_name=account_name,
                    sub_name=_to_text(row.get("sub_name")),
                    contact_notes=_to_text(row.get("contact_notes")),
                    sort_order=_to_int(row.get("sort_order")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return results

    def fetch_delivery_logs(self, updated_at: datetime | None) -> list[CmDataDeliveryLog]:
        rows = self._fetch_table_rows(
            "delivery_log",
            [
                "id",
                "location_id",
                "location_name",
                "status",
                "units",
                "discord_id",
                "discord_name",
                "notes",
                "edit_notes",
                "ocr_notes",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataDeliveryLog] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="delivery_log.id")
            location_name = _require_text(row.get("location_name"), field_name="delivery_log.location_name")
            status = _require_text(row.get("status"), field_name="delivery_log.status")
            results.append(
                CmDataDeliveryLog(
                    record_id=record_id,
                    location_id=_to_int(row.get("location_id")),
                    location_name=location_name,
                    status=status,
                    units=_to_int(row.get("units")) or 0,
                    discord_id=_to_int(row.get("discord_id")),
                    discord_name=_to_text(row.get("discord_name")),
                    notes=_to_text(row.get("notes")),
                    edit_notes=_to_text(row.get("edit_notes")),
                    ocr_notes=_to_text(row.get("ocr_notes")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return results

    def _fetch_table_rows(
        self,
        table: str,
        columns: list[str],
        *,
        updated_at: datetime | None,
    ) -> list[RowData]:
        column_list = ", ".join(f"`{column}`" for column in columns)
        query = f"SELECT {column_list} FROM `{self._database}`.`{table}`"
        parameters: list[QueryParameter] = []
        if updated_at:
            query = f"{query} WHERE `updated_at` >= %s"
            parameters.append(updated_at)
        return self._fetch_rows(query, parameters or None)

    def _fetch_rows(self, query: str, parameters: Sequence[QueryParameter] | None) -> list[RowData]:
        for attempt in range(2):
            connection = self._require_connection()
            try:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(query, parameters)
                    rows = [dict(row) for row in cursor.fetchall()]
                return rows
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as exc:
                error_code = exc.args[0] if exc.args else None
                if error_code not in {2006, 2013} or attempt:
                    raise
                _logger.warning("CM data sync connection dropped; reconnecting and retrying query.")
                self.close()
        return []

    # noinspection DuplicatedCode
    # Mirrors RepairShopr SSL handling to keep connection logic self-contained.
    def _open_connection(self) -> pymysql.connections.Connection:
        secure_context: ssl.SSLContext | None = None
        if self._settings.use_ssl:
            secure_context = ssl.create_default_context()
            if not self._settings.ssl_verify:
                secure_context.check_hostname = False
                secure_context.verify_mode = ssl.CERT_NONE
        connect_args = {
            "host": self._settings.host,
            "user": self._settings.user,
            "password": self._settings.password,
            "port": self._settings.port,
            "connect_timeout": 10,
            "charset": "utf8mb4",
            "autocommit": True,
            "ssl": secure_context,
        }
        if self._settings.database:
            connect_args["database"] = self._settings.database
        connection = pymysql.connect(**connect_args)
        self._configure_session(connection)
        return connection

    @staticmethod
    def _configure_session(connection: pymysql.connections.Connection) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET time_zone = '+00:00'")
        except pymysql.MySQLError:
            _logger.warning("CM data connection did not accept time_zone override; continuing without it.")

    def _require_connection(self) -> pymysql.connections.Connection:
        if self._connection is None:
            self._connection = self._open_connection()
        return self._connection


def _to_text(value: RawValue) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_text(value: RawValue, *, field_name: str) -> str:
    text = _to_text(value)
    if not text:
        raise ValueError(f"Missing required text for {field_name}.")
    return text


def _to_int(value: RawValue) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return int(bytes(value).decode().strip())
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _require_int(value: RawValue, *, field_name: str) -> int:
    parsed = _to_int(value)
    if parsed is None:
        raise ValueError(f"Missing required integer for {field_name}.")
    return parsed


def _to_datetime(value: RawValue) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# noinspection DuplicatedCode
# Localized boolean coercion to avoid cross-addon coupling.
def _to_bool(value: RawValue) -> bool:
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
        return _to_bool(decoded)
    if isinstance(value, (int, float)):
        return bool(value)
    value_str = str(value).strip().lower()
    return value_str in {"1", "true", "yes", "on", "y", "t"}
