from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType

import pymysql
from odoo.addons.external_ids.utils.ssl_context import build_ssl_context

_logger = logging.getLogger(__name__)


SCHOOL_INFORMATION_DATABASE = "school_information"
PRICING_DATABASE = "pricing"


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
    ticket_name_report: str | None
    rs_customer_id: str | None
    label_names: str | None
    claim_name_list: str | None
    multi_building_flag: bool
    price_list: str | None
    price_list_2: str | None
    priority_flag: bool
    on_delivery_schedule: bool
    shipping_enable: bool
    location_drop: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataAccountNameResult:
    rows: list[CmDataAccountName]
    rs_customer_id_available: bool


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


@dataclass(frozen=True)
class CmDataDirection:
    record_id: int
    account_name: str
    ticket_title_name: str
    school_name: str
    delivery_day: str | None
    address: str | None
    directions: str | None
    contact: str | None
    priority: bool
    on_schedule_flag: bool
    delivery_order: float | None
    longitude: float | None
    latitude: float | None
    available_start: str | None
    available_end: str | None
    break_start: str | None
    break_end: str | None
    est_arrival_time: str | None
    shipping_enabled_flag: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataShippingInstruction:
    record_id: int
    account_name: str
    address_key: str
    inbound_carrier: str | None
    inbound_service: str | None
    outbound_carrier: str | None
    outbound_service: str | None
    to_address_name: str | None
    to_address_company: str | None
    to_address_street1: str | None
    to_address_street2: str | None
    to_address_city: str | None
    to_address_state: str | None
    to_address_zip: str | None
    to_address_country: str | None
    to_address_phone: str | None
    to_address_email: str | None
    to_address_residential_flag: bool
    parcel_length: float | None
    parcel_width: float | None
    parcel_height: float | None
    parcel_weight: float | None
    options_print_custom_1: str | None
    options_print_custom_2: str | None
    options_label_format: str | None
    options_label_size: str | None
    options_hazmat: str | None


@dataclass(frozen=True)
class CmDataNoteRow:
    record_id: int
    account_name: str
    sub_name: str | None
    note: str | None
    sort_order: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataPassword:
    account_name: str
    sub_name: str | None
    user_name: str | None
    password: str | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataPriceList:
    record_id: int
    link: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataPricingCatalog:
    record_id: int
    code: str
    name: str
    partner_label: str | None
    active: bool
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataPricingLine:
    record_id: int
    catalog_id: int
    model_label: str
    repair_label: str
    price: float | None
    currency: str | None
    active: bool
    source_batch: str | None
    source_file: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataModelNumber:
    record_id: int
    model: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CmDataEmployee:
    record_id: int
    legal_name: str | None
    legal_last: str | None
    legal_first: str | None
    name: str | None
    repairshopr_id: int | None
    timeclock_id: int | None
    discord_id: int | None
    grafana_username: str | None
    date_of_hire: datetime | None
    date_of_birth: datetime | None
    last_day: datetime | None
    dept: str | None
    team: str | None
    active: bool
    on_site: bool


# noinspection DuplicatedCode
# Duplicate field lists mirror CM Data PTO/Vacation schemas.
@dataclass(frozen=True)
class CmDataPtoUsage:
    record_id: int
    used_at: datetime | None
    updated_at: datetime | None
    pay_period_ending: datetime | None
    employee_id: int | None
    name: str | None
    usage: float | None
    notes: str | None
    added_by: str | None


# noinspection DuplicatedCode
# Duplicate field lists mirror CM Data PTO/Vacation schemas.
@dataclass(frozen=True)
class CmDataVacationUsage:
    record_id: int
    created_at: datetime | None
    updated_at: datetime | None
    date_of: datetime | None
    employee_id: int | None
    name: str | None
    usage_hours: float | None
    notes: str | None
    added_by: str | None


@dataclass(frozen=True)
class CmDataTimeclockPunch:
    record_id: int
    compnum: int | None
    user_id: int | None
    check_type: str | None
    check_time: datetime | None
    sensor_id: str | None
    checked: str | None
    reason: str | None
    work_type: int | None
    check_number: str | None
    created_by: str | None
    edited_by: str | None
    created_date: datetime | None
    edited_day: datetime | None
    locked: bool
    time_received: datetime | None
    exception: str | None
    dept_code: int | None
    comment: str | None


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

    def fetch_account_names(self, updated_at: datetime | None) -> CmDataAccountNameResult:
        columns = [
            "id",
            "account_name",
            "ticket_name",
            "ticket_name_report",
            "rs_customer_id",
            "label_names",
            "claim_name_list",
            "multi_building_flag",
            "price_list",
            "price_list_2",
            "priority_flag",
            "on_delivery_schedule",
            "shipping_enable",
            "location_drop",
            "updated_at",
        ]
        rs_customer_id_available = True
        try:
            rows = self._fetch_table_rows(
                "account_names",
                columns,
                updated_at=updated_at,
            )
        except pymysql.err.ProgrammingError as exc:
            if "rs_customer_id" not in str(exc).lower():
                raise
            rs_customer_id_available = False
            fallback_columns = [column for column in columns if column != "rs_customer_id"]
            rows = self._fetch_table_rows(
                "account_names",
                fallback_columns,
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
                    ticket_name_report=_to_text(row.get("ticket_name_report")),
                    rs_customer_id=_to_text(row.get("rs_customer_id")),
                    label_names=_to_text(row.get("label_names")),
                    claim_name_list=_to_text(row.get("claim_name_list")),
                    multi_building_flag=_to_bool(row.get("multi_building_flag")),
                    price_list=_to_text(row.get("price_list")),
                    price_list_2=_to_text(row.get("price_list_2")),
                    priority_flag=_to_bool(row.get("priority_flag")),
                    on_delivery_schedule=_to_bool(row.get("on_delivery_schedule")),
                    shipping_enable=_to_bool(row.get("shipping_enable")),
                    location_drop=_to_text(row.get("location_drop")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return CmDataAccountNameResult(
            rows=results,
            rs_customer_id_available=rs_customer_id_available,
        )


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

    def fetch_directions(self, updated_at: datetime | None) -> list[CmDataDirection]:
        rows = self._fetch_table_rows(
            "directions",
            [
                "id",
                "account_name",
                "ticket_title_name",
                "school_name",
                "delivery_day",
                "address",
                "directions",
                "contact",
                "priority",
                "on_schedule_flag",
                "delivery_order",
                "longitude",
                "latitude",
                "available_start",
                "available_end",
                "break_start",
                "break_end",
                "est_arrival_time",
                "shipping_enabled_flag",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataDirection] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="directions.id")
            account_name = _require_text(row.get("account_name"), field_name="directions.account_name")
            ticket_title_name = _to_text(row.get("ticket_title_name")) or account_name
            school_name = _to_text(row.get("school_name")) or account_name
            results.append(
                CmDataDirection(
                    record_id=record_id,
                    account_name=account_name,
                    ticket_title_name=ticket_title_name,
                    school_name=school_name,
                    delivery_day=_to_text(row.get("delivery_day")),
                    address=_to_text(row.get("address")),
                    directions=_to_text(row.get("directions")),
                    contact=_to_text(row.get("contact")),
                    priority=_to_bool(row.get("priority")),
                    on_schedule_flag=_to_bool(row.get("on_schedule_flag")),
                    delivery_order=_to_float(row.get("delivery_order")),
                    longitude=_to_float(row.get("longitude")),
                    latitude=_to_float(row.get("latitude")),
                    available_start=_to_text(row.get("available_start")),
                    available_end=_to_text(row.get("available_end")),
                    break_start=_to_text(row.get("break_start")),
                    break_end=_to_text(row.get("break_end")),
                    est_arrival_time=_to_text(row.get("est_arrival_time")),
                    shipping_enabled_flag=_to_bool(row.get("shipping_enabled_flag")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return results

    def fetch_shipping_instructions(self, updated_at: datetime | None) -> list[CmDataShippingInstruction]:
        rows = self._fetch_table_rows(
            "shipping_instructions",
            [
                "id",
                "account_name",
                "address_key",
                "inbound_carrier",
                "inbound_service",
                "outbound_carrier",
                "outbound_service",
                "to_address_name",
                "to_address_company",
                "to_address_street1",
                "to_address_street2",
                "to_address_city",
                "to_address_state",
                "to_address_zip",
                "to_address_country",
                "to_address_phone",
                "to_address_email",
                "to_address_residential_flag",
                "parcel_length",
                "parcel_width",
                "parcel_height",
                "parcel_weight",
                "options_print_custom_1",
                "options_print_custom_2",
                "options_label_format",
                "options_label_size",
                "options_hazmat",
            ],
            updated_at=updated_at,
            updated_column=None,
        )
        results: list[CmDataShippingInstruction] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="shipping_instructions.id")
            account_name = _require_text(
                row.get("account_name"),
                field_name="shipping_instructions.account_name",
            )
            address_key = _require_text(
                row.get("address_key"),
                field_name="shipping_instructions.address_key",
            )
            results.append(
                CmDataShippingInstruction(
                    record_id=record_id,
                    account_name=account_name,
                    address_key=address_key,
                    inbound_carrier=_to_text(row.get("inbound_carrier")),
                    inbound_service=_to_text(row.get("inbound_service")),
                    outbound_carrier=_to_text(row.get("outbound_carrier")),
                    outbound_service=_to_text(row.get("outbound_service")),
                    to_address_name=_to_text(row.get("to_address_name")),
                    to_address_company=_to_text(row.get("to_address_company")),
                    to_address_street1=_to_text(row.get("to_address_street1")),
                    to_address_street2=_to_text(row.get("to_address_street2")),
                    to_address_city=_to_text(row.get("to_address_city")),
                    to_address_state=_to_text(row.get("to_address_state")),
                    to_address_zip=_to_text(row.get("to_address_zip")),
                    to_address_country=_to_text(row.get("to_address_country")),
                    to_address_phone=_to_text(row.get("to_address_phone")),
                    to_address_email=_to_text(row.get("to_address_email")),
                    to_address_residential_flag=_to_bool(row.get("to_address_residential_flag")),
                    parcel_length=_to_float(row.get("parcel_length")),
                    parcel_width=_to_float(row.get("parcel_width")),
                    parcel_height=_to_float(row.get("parcel_height")),
                    parcel_weight=_to_float(row.get("parcel_weight")),
                    options_print_custom_1=_to_text(row.get("options_print_custom_1")),
                    options_print_custom_2=_to_text(row.get("options_print_custom_2")),
                    options_label_format=_to_text(row.get("options_label_format")),
                    options_label_size=_to_text(row.get("options_label_size")),
                    options_hazmat=_to_text(row.get("options_hazmat")),
                )
            )
        return results

    def fetch_intake_notes(self, updated_at: datetime | None) -> list[CmDataNoteRow]:
        return self._fetch_note_rows("intake", "intake_notes", updated_at)

    def fetch_diagnostic_notes(self, updated_at: datetime | None) -> list[CmDataNoteRow]:
        return self._fetch_note_rows("diagnostics", "diagnostic_notes", updated_at)

    def fetch_repair_notes(self, updated_at: datetime | None) -> list[CmDataNoteRow]:
        return self._fetch_note_rows("repair", "repair_notes", updated_at)

    def fetch_quality_control_notes(self, updated_at: datetime | None) -> list[CmDataNoteRow]:
        return self._fetch_note_rows("qc", "qc_notes", updated_at)

    def fetch_invoice_notes(self, updated_at: datetime | None) -> list[CmDataNoteRow]:
        return self._fetch_note_rows("invoice", "invoice_notes", updated_at)

    def fetch_passwords(self, updated_at: datetime | None) -> list[CmDataPassword]:
        rows = self._fetch_table_rows(
            "passwords",
            [
                "account_name",
                "sub_name",
                "user_name",
                "password",
                "notes",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataPassword] = []
        for row in rows:
            account_name = _require_text(row.get("account_name"), field_name="passwords.account_name")
            sub_name = _to_text(row.get("sub_name"))
            updated_at_value = _to_datetime(row.get("updated_at")) or _to_datetime(row.get("created_at"))
            results.append(
                CmDataPassword(
                    account_name=account_name,
                    sub_name=sub_name,
                    user_name=_to_text(row.get("user_name")),
                    password=_to_text(row.get("password")),
                    notes=_to_text(row.get("notes")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=updated_at_value,
                )
            )
        return results

    def fetch_price_lists(self, updated_at: datetime | None) -> list[CmDataPriceList]:
        rows = self._fetch_table_rows(
            "price_lists",
            [
                "id",
                "link",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataPriceList] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="price_lists.id")
            updated_at_value = _to_datetime(row.get("updated_at")) or _to_datetime(row.get("created_at"))
            results.append(
                CmDataPriceList(
                    record_id=record_id,
                    link=_to_text(row.get("link")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=updated_at_value,
                )
            )
        return results

    def fetch_pricing_catalogs(self, updated_at: datetime | None) -> list[CmDataPricingCatalog]:
        rows = self._fetch_table_rows(
            "pricing_catalog",
            [
                "id",
                "code",
                "name",
                "partner_label",
                "active",
                "notes",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
            database=PRICING_DATABASE,
        )
        results: list[CmDataPricingCatalog] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="pricing_catalog.id")
            updated_at_value = _to_datetime(row.get("updated_at")) or _to_datetime(row.get("created_at"))
            results.append(
                CmDataPricingCatalog(
                    record_id=record_id,
                    code=_require_text(row.get("code"), field_name="pricing_catalog.code"),
                    name=_require_text(row.get("name"), field_name="pricing_catalog.name"),
                    partner_label=_to_text(row.get("partner_label")),
                    active=_to_bool(row.get("active")),
                    notes=_to_text(row.get("notes")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=updated_at_value,
                )
            )
        return results

    def fetch_pricing_lines(self, updated_at: datetime | None) -> list[CmDataPricingLine]:
        rows = self._fetch_table_rows(
            "pricing_line",
            [
                "id",
                "catalog_id",
                "model_label",
                "repair_label",
                "price",
                "currency",
                "active",
                "source_batch",
                "source_file",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
            database=PRICING_DATABASE,
        )
        results: list[CmDataPricingLine] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="pricing_line.id")
            updated_at_value = _to_datetime(row.get("updated_at")) or _to_datetime(row.get("created_at"))
            results.append(
                CmDataPricingLine(
                    record_id=record_id,
                    catalog_id=_require_int(row.get("catalog_id"), field_name="pricing_line.catalog_id"),
                    model_label=_require_text(row.get("model_label"), field_name="pricing_line.model_label"),
                    repair_label=_require_text(row.get("repair_label"), field_name="pricing_line.repair_label"),
                    price=_to_float(row.get("price")),
                    currency=_to_text(row.get("currency")),
                    active=_to_bool(row.get("active")),
                    source_batch=_to_text(row.get("source_batch")),
                    source_file=_to_text(row.get("source_file")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=updated_at_value,
                )
            )
        return results

    def fetch_model_numbers(self, updated_at: datetime | None) -> list[CmDataModelNumber]:
        rows = self._fetch_table_rows(
            "model_numbers",
            [
                "id",
                "model",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataModelNumber] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="model_numbers.id")
            model = _require_text(row.get("model"), field_name="model_numbers.model")
            results.append(
                CmDataModelNumber(
                    record_id=record_id,
                    model=model,
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=_to_datetime(row.get("updated_at")),
                )
            )
        return results

    def fetch_employees(self, updated_at: datetime | None) -> list[CmDataEmployee]:
        rows = self._fetch_table_rows(
            "employees",
            [
                "id",
                "legal_name",
                "legal_last",
                "legal_first",
                "name",
                "repairshopr_id",
                "timeclock_id",
                "discord_id",
                "grafana_username",
                "date_of_hire",
                "date_of_birth",
                "last_day",
                "dept",
                "team",
                "active",
                "on_site",
            ],
            updated_at=updated_at,
            updated_column=None,
            database="employee",
        )
        results: list[CmDataEmployee] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="employees.id")
            results.append(
                CmDataEmployee(
                    record_id=record_id,
                    legal_name=_to_text(row.get("legal_name")),
                    legal_last=_to_text(row.get("legal_last")),
                    legal_first=_to_text(row.get("legal_first")),
                    name=_to_text(row.get("name")),
                    repairshopr_id=_to_int(row.get("repairshopr_id")),
                    timeclock_id=_to_int(row.get("timeclock_id")),
                    discord_id=_to_int(row.get("discord_id")),
                    grafana_username=_to_text(row.get("grafana_username")),
                    date_of_hire=_to_datetime(row.get("date_of_hire")),
                    date_of_birth=_to_datetime(row.get("date_of_birth")),
                    last_day=_to_datetime(row.get("last_day")),
                    dept=_to_text(row.get("dept")),
                    team=_to_text(row.get("team")),
                    active=_to_bool(row.get("active")),
                    on_site=_to_bool(row.get("on_site")),
                )
            )
        return results

    def fetch_pto_usage(self, updated_at: datetime | None) -> list[CmDataPtoUsage]:
        rows = self._fetch_table_rows(
            "pto_usage",
            [
                "id",
                "used_at",
                "updated_at",
                "pay_period_ending",
                "employee_id",
                "name",
                "usage",
                "notes",
                "added_by",
            ],
            updated_at=updated_at,
            database="employee",
        )
        results: list[CmDataPtoUsage] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="pto_usage.id")
            results.append(
                CmDataPtoUsage(
                    record_id=record_id,
                    used_at=_to_datetime(row.get("used_at")),
                    updated_at=_to_datetime(row.get("updated_at")),
                    pay_period_ending=_to_datetime(row.get("pay_period_ending")),
                    employee_id=_to_int(row.get("employee_id")),
                    name=_to_text(row.get("name")),
                    usage=_to_float(row.get("usage")),
                    notes=_to_text(row.get("notes")),
                    added_by=_to_text(row.get("added_by")),
                )
            )
        return results

    def fetch_vacation_usage(self, updated_at: datetime | None) -> list[CmDataVacationUsage]:
        rows = self._fetch_table_rows(
            "vacation_usage",
            [
                "id",
                "created_at",
                "updated_at",
                "date_of",
                "employee_id",
                "name",
                "vacation_usage_hours",
                "notes",
                "added_by",
            ],
            updated_at=updated_at,
            database="employee",
        )
        results: list[CmDataVacationUsage] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="vacation_usage.id")
            results.append(
                CmDataVacationUsage(
                    record_id=record_id,
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=_to_datetime(row.get("updated_at")),
                    date_of=_to_datetime(row.get("date_of")),
                    employee_id=_to_int(row.get("employee_id")),
                    name=_to_text(row.get("name")),
                    usage_hours=_to_float(row.get("vacation_usage_hours")),
                    notes=_to_text(row.get("notes")),
                    added_by=_to_text(row.get("added_by")),
                )
            )
        return results

    def fetch_timeclock_punches(self, updated_at: datetime | None) -> list[CmDataTimeclockPunch]:
        rows = self._fetch_table_rows(
            "timeclock_punches",
            [
                "id",
                "compnum",
                "user_id",
                "check_type",
                "check_time",
                "sensor_id",
                "checked",
                "reason",
                "work_type",
                "check_number",
                "created_by",
                "edited_by",
                "created_date",
                "edited_day",
                "locked",
                "time_received",
                "exception",
                "dept_code",
                "comment",
            ],
            updated_at=updated_at,
            updated_column=None,
            database="payroll-report",
        )
        results: list[CmDataTimeclockPunch] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name="timeclock_punches.id")
            results.append(
                CmDataTimeclockPunch(
                    record_id=record_id,
                    compnum=_to_int(row.get("compnum")),
                    user_id=_to_int(row.get("user_id")),
                    check_type=_to_text(row.get("check_type")),
                    check_time=_to_datetime(row.get("check_time")),
                    sensor_id=_to_text(row.get("sensor_id")),
                    checked=_to_text(row.get("checked")),
                    reason=_to_text(row.get("reason")),
                    work_type=_to_int(row.get("work_type")),
                    check_number=_to_text(row.get("check_number")),
                    created_by=_to_text(row.get("created_by")),
                    edited_by=_to_text(row.get("edited_by")),
                    created_date=_to_datetime(row.get("created_date")),
                    edited_day=_to_datetime(row.get("edited_day")),
                    locked=_to_bool(row.get("locked")),
                    time_received=_to_datetime(row.get("time_received")),
                    exception=_to_text(row.get("exception")),
                    dept_code=_to_int(row.get("dept_code")),
                    comment=_to_text(row.get("comment")),
                )
            )
        return results

    def _fetch_note_rows(self, table: str, note_column: str, updated_at: datetime | None) -> list[CmDataNoteRow]:
        rows = self._fetch_table_rows(
            table,
            [
                "id",
                "account_name",
                "sub_name",
                note_column,
                "sort_order",
                "created_at",
                "updated_at",
            ],
            updated_at=updated_at,
        )
        results: list[CmDataNoteRow] = []
        for row in rows:
            record_id = _require_int(row.get("id"), field_name=f"{table}.id")
            account_name = _require_text(row.get("account_name"), field_name=f"{table}.account_name")
            updated_at_value = _to_datetime(row.get("updated_at")) or _to_datetime(row.get("created_at"))
            results.append(
                CmDataNoteRow(
                    record_id=record_id,
                    account_name=account_name,
                    sub_name=_to_text(row.get("sub_name")),
                    note=_to_text(row.get(note_column)),
                    sort_order=_to_int(row.get("sort_order")),
                    created_at=_to_datetime(row.get("created_at")),
                    updated_at=updated_at_value,
                )
            )
        return results

    def _fetch_table_rows(
        self,
        table: str,
        columns: list[str],
        *,
        updated_at: datetime | None,
        updated_column: str | None = "updated_at",
        database: str | None = None,
    ) -> list[RowData]:
        column_list = ", ".join(f"`{column}`" for column in columns)
        database_name = database or self._database
        query = f"SELECT {column_list} FROM `{database_name}`.`{table}`"
        parameters: list[QueryParameter] = []
        if updated_at and updated_column:
            query = f"{query} WHERE `{updated_column}` >= %s"
            parameters.append(updated_at)
        return self._fetch_rows(query, parameters or None)

    def _fetch_rows(self, query: str, parameters: Sequence[QueryParameter] | None) -> list[RowData]:
        for attempt in range(2):
            if self._connection is None:
                self._connection = self._open_connection()
            connection = self._connection
            if connection is None:
                raise RuntimeError("CM data connection unavailable.")
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

    def _open_connection(self) -> pymysql.connections.Connection:
        secure_context = build_ssl_context(self._settings.use_ssl, self._settings.ssl_verify)
        connection = pymysql.connect(
            host=self._settings.host,
            user=self._settings.user,
            password=self._settings.password,
            port=self._settings.port,
            charset="utf8mb4",
            autocommit=True,
            database=self._settings.database or None,
            ssl=secure_context,
        )
        self._configure_session(connection)
        return connection

    @staticmethod
    def _configure_session(connection: pymysql.connections.Connection) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET time_zone = '+00:00'")
        except pymysql.MySQLError:
            _logger.warning("CM data connection did not accept time_zone override; continuing without it.")

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


def _to_float(value: RawValue) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return float(bytes(value).decode().strip())
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


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
