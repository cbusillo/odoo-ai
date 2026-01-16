import logging
import ssl
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, overload

import pymysql

from . import repairshopr_sync_models as repairshopr_models


CUSTOMER_TABLE = "repairshopr_data_customer"
CONTACT_TABLE = "repairshopr_data_customercontact"
PRODUCT_TABLE = "repairshopr_data_product"
TICKET_TABLE = "repairshopr_data_ticket"
TICKET_PROPERTIES_TABLE = "repairshopr_data_ticketproperties"
TICKET_COMMENT_TABLE = "repairshopr_data_ticketcomment"
ESTIMATE_TABLE = "repairshopr_data_estimate"
ESTIMATE_LINE_ITEM_TABLE = "repairshopr_data_estimatelineitem"
INVOICE_TABLE = "repairshopr_data_invoice"
INVOICE_LINE_ITEM_TABLE = "repairshopr_data_invoicelineitem"


_logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RepairshoprSyncConnectionSettings:
    host: str
    user: str
    password: str
    database: str
    port: int = 3306
    use_ssl: bool = True
    ssl_verify: bool = True
    batch_size: int = 500


class RepairshoprSyncClient:
    def __init__(self, settings: RepairshoprSyncConnectionSettings) -> None:
        self._settings = settings
        self._connection: pymysql.connections.Connection | None = None

    def __enter__(self) -> "RepairshoprSyncClient":
        self._connection = self._open_connection()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def clear_cache(self) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    @overload
    def get_model(
        self,
        model_type: type[repairshopr_models.Customer],
        *,
        updated_at: datetime | None = None,
    ) -> Iterable[repairshopr_models.Customer]:
        ...

    @overload
    def get_model(
        self,
        model_type: type[repairshopr_models.Product],
        *,
        updated_at: datetime | None = None,
    ) -> Iterable[repairshopr_models.Product]:
        ...

    @overload
    def get_model(
        self,
        model_type: type[repairshopr_models.Ticket],
        *,
        updated_at: datetime | None = None,
    ) -> Iterable[repairshopr_models.Ticket]:
        ...

    @overload
    def get_model(
        self,
        model_type: type[repairshopr_models.Estimate],
        *,
        updated_at: datetime | None = None,
    ) -> Iterable[repairshopr_models.Estimate]:
        ...

    @overload
    def get_model(
        self,
        model_type: type[repairshopr_models.Invoice],
        *,
        updated_at: datetime | None = None,
    ) -> Iterable[repairshopr_models.Invoice]:
        ...

    def get_model(self, model_type: type[object], *, updated_at: datetime | None = None) -> Iterable[object]:
        if model_type is repairshopr_models.Customer:
            return self._iter_customers(updated_at)
        if model_type is repairshopr_models.Product:
            return self._iter_products(updated_at)
        if model_type is repairshopr_models.Ticket:
            return self._iter_tickets(updated_at)
        if model_type is repairshopr_models.Estimate:
            return self._iter_estimates(updated_at)
        if model_type is repairshopr_models.Invoice:
            return self._iter_invoices(updated_at)
        raise ValueError(f"Unsupported model type: {model_type}")

    def fetch_line_items(
        self,
        *,
        estimate_id: int | None = None,
        invoice_id: int | None = None,
    ) -> list[dict[str, object]]:
        if estimate_id:
            return self._fetch_estimate_line_items(estimate_id)
        if invoice_id:
            return self._fetch_invoice_line_items(invoice_id)
        return []

    def _iter_customers(self, updated_at: datetime | None) -> Iterator[repairshopr_models.Customer]:
        for rows in self._iter_batches(
            CUSTOMER_TABLE,
            [
                "id",
                "firstname",
                "lastname",
                "fullname",
                "business_name",
                "email",
                "phone",
                "mobile",
                "address",
                "address_2",
                "city",
                "state",
                "zip",
                "notes",
                "disabled",
                "no_email",
            ],
            updated_at=updated_at,
            updated_column="updated_at",
            created_column="created_at",
        ):
            customer_ids = [
                customer_id
                for row in rows
                if (customer_id := _to_int(row.get("id"))) is not None
            ]
            contacts_by_customer = self._fetch_contacts(customer_ids)
            for row in rows:
                customer_id = _to_int(row.get("id"))
                if customer_id is None:
                    contacts = []
                else:
                    contacts = contacts_by_customer.get(customer_id, [])
                yield self._build_customer(row, contacts)

    def _iter_products(self, updated_at: datetime | None) -> Iterator[repairshopr_models.Product]:
        if updated_at is not None:
            _logger.info("RepairShopr product sync rows do not track updated_at; ignoring filter.")
        for rows in self._iter_batches(
            PRODUCT_TABLE,
            [
                "id",
                "price_cost",
                "price_retail",
                "description",
                "name",
                "disabled",
                "product_category",
                "category_path",
                "upc_code",
                "long_description",
            ],
            updated_at=None,
            updated_column=None,
            created_column=None,
        ):
            for row in rows:
                yield self._build_product(row)

    def _iter_tickets(self, updated_at: datetime | None) -> Iterator[repairshopr_models.Ticket]:
        updated_value = self._format_updated_at(updated_at, treat_as_text=True)
        for rows in self._iter_batches(
            TICKET_TABLE,
            [
                "id",
                "number",
                "subject",
                "created_at",
                "customer_id",
                "customer_business_then_name",
                "problem_type",
                "status",
                "priority",
                "properties_id",
                "updated_at",
            ],
            updated_at=updated_value,
            updated_column="updated_at",
            created_column="created_at",
        ):
            ticket_ids = [
                ticket_id
                for row in rows
                if (ticket_id := _to_int(row.get("id"))) is not None
            ]
            properties_ids = [
                properties_id
                for row in rows
                if (properties_id := _to_int(row.get("properties_id"))) is not None
            ]
            properties_by_id = self._fetch_ticket_properties(properties_ids)
            comments_by_ticket = self._fetch_ticket_comments(ticket_ids)
            for row in rows:
                properties_id = _to_int(row.get("properties_id"))
                ticket_id = _to_int(row.get("id"))
                if properties_id is None:
                    properties = repairshopr_models.TicketProperties()
                else:
                    properties = properties_by_id.get(properties_id) or repairshopr_models.TicketProperties()
                comments = comments_by_ticket.get(ticket_id, []) if ticket_id is not None else []
                yield self._build_ticket(row, properties, comments)

    def _iter_estimates(self, updated_at: datetime | None) -> Iterator[repairshopr_models.Estimate]:
        for rows in self._iter_batches(
            ESTIMATE_TABLE,
            [
                "id",
                "customer_id",
                "customer_business_then_name",
                "number",
                "created_at",
                "date",
                "employee",
            ],
            updated_at=updated_at,
            updated_column="updated_at",
            created_column="created_at",
        ):
            for row in rows:
                yield self._build_estimate(row)

    def _iter_invoices(self, updated_at: datetime | None) -> Iterator[repairshopr_models.Invoice]:
        for rows in self._iter_batches(
            INVOICE_TABLE,
            [
                "id",
                "customer_id",
                "customer_business_then_name",
                "number",
                "created_at",
                "date",
                "due_date",
                "note",
            ],
            updated_at=updated_at,
            updated_column="updated_at",
            created_column="created_at",
        ):
            for row in rows:
                yield self._build_invoice(row)

    def _iter_batches(
        self,
        table: str,
        columns: Sequence[str],
        *,
        updated_at: datetime | str | None,
        updated_column: str | None,
        created_column: str | None,
    ) -> Iterator[list[dict[str, object]]]:
        last_seen_id = 0
        while True:
            where_fragments = ["id > %s"]
            parameters: list[object] = [last_seen_id]
            if updated_at is not None and updated_column:
                if created_column:
                    where_fragments.append(f"({updated_column} >= %s OR {created_column} >= %s)")
                    parameters.extend([updated_at, updated_at])
                else:
                    where_fragments.append(f"{updated_column} >= %s")
                    parameters.append(updated_at)
            where_clause = " AND ".join(where_fragments)
            column_clause = ", ".join(columns)
            query = (
                f"SELECT {column_clause} FROM {table} "
                f"WHERE {where_clause} ORDER BY id LIMIT %s"
            )
            parameters.append(self._settings.batch_size)
            rows = self._fetch_rows(query, parameters)
            if not rows:
                break
            yield rows
            last_seen_id = rows[-1]["id"]

    def _fetch_contacts(self, customer_ids: Sequence[int]) -> dict[int, list[repairshopr_models.Contact]]:
        contacts_by_customer: dict[int, list[repairshopr_models.Contact]] = defaultdict(list)
        for batch in chunk_values(customer_ids, self._settings.batch_size):
            placeholders = ", ".join(["%s"] * len(batch))
            query = (
                "SELECT id, name, address1, address2, city, state, zip, email, phone, mobile, notes, "
                "extension, processed_phone, processed_mobile, parent_customer_id "
                f"FROM {CONTACT_TABLE} WHERE parent_customer_id IN ({placeholders})"
            )
            rows = self._fetch_rows(query, batch)
            for row in rows:
                customer_id = row.get("parent_customer_id")
                if not isinstance(customer_id, int):
                    continue
                contacts_by_customer[customer_id].append(self._build_contact(row))
        return contacts_by_customer

    def _fetch_ticket_properties(self, properties_ids: Sequence[int]) -> dict[int, repairshopr_models.TicketProperties]:
        properties_by_id: dict[int, repairshopr_models.TicketProperties] = {}
        for batch in chunk_values(properties_ids, self._settings.batch_size):
            placeholders = ", ".join(["%s"] * len(batch))
            query = (
                "SELECT id, day, `case`, other, s_n_num, tag_num, claim_num, location, transport, boces, "
                "tag_num_2, delivery_num, transport_2, po_num_2, phone_num, p_g_name, student, s_n, "
                "drop_off_location, call_num "
                f"FROM {TICKET_PROPERTIES_TABLE} WHERE id IN ({placeholders})"
            )
            rows = self._fetch_rows(query, batch)
            for row in rows:
                properties = self._build_ticket_properties(row)
                if properties.id is not None:
                    properties_by_id[properties.id] = properties
        return properties_by_id

    def _fetch_ticket_comments(self, ticket_ids: Sequence[int]) -> dict[int, list[repairshopr_models.TicketComment]]:
        comments_by_ticket: dict[int, list[repairshopr_models.TicketComment]] = defaultdict(list)
        for batch in chunk_values(ticket_ids, self._settings.batch_size):
            placeholders = ", ".join(["%s"] * len(batch))
            query = (
                "SELECT id, created_at, subject, body, tech, hidden, ticket_id "
                f"FROM {TICKET_COMMENT_TABLE} WHERE ticket_id IN ({placeholders}) ORDER BY id"
            )
            rows = self._fetch_rows(query, batch)
            for row in rows:
                ticket_id = row.get("ticket_id")
                if not isinstance(ticket_id, int):
                    continue
                comments_by_ticket[ticket_id].append(self._build_ticket_comment(row))
        return comments_by_ticket

    def _fetch_estimate_line_items(self, estimate_id: int) -> list[dict[str, object]]:
        return self._fetch_line_items_for_parent(
            table=ESTIMATE_LINE_ITEM_TABLE,
            parent_column="parent_estimate_id",
            parent_id=estimate_id,
        )

    def _fetch_invoice_line_items(self, invoice_id: int) -> list[dict[str, object]]:
        return self._fetch_line_items_for_parent(
            table=INVOICE_LINE_ITEM_TABLE,
            parent_column="parent_invoice_id",
            parent_id=invoice_id,
        )

    def _fetch_line_items_for_parent(self, *, table: str, parent_column: str, parent_id: int) -> list[dict[str, object]]:
        query = (
            "SELECT id, product_id, item, name, price, quantity, discount_percent "
            f"FROM {table} WHERE {parent_column} = %s ORDER BY id"
        )
        rows = self._fetch_rows(query, [parent_id])
        return [self._build_line_item(row) for row in rows]

    def _fetch_rows(self, query: str, parameters: Sequence[object] | None = None) -> list[dict[str, Any]]:
        connection = self._require_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()
        return list(rows)

    # noinspection DuplicatedCode
    # Mirrors Fishbowl SSL handling to keep connection logic self-contained.
    def _open_connection(self) -> pymysql.connections.Connection:
        secure_context: ssl.SSLContext | None = None
        if self._settings.use_ssl:
            secure_context = ssl.create_default_context()
            if not self._settings.ssl_verify:
                secure_context.check_hostname = False
                secure_context.verify_mode = ssl.CERT_NONE
        return pymysql.connect(
            host=self._settings.host,
            user=self._settings.user,
            password=self._settings.password,
            database=self._settings.database,
            port=self._settings.port,
            charset="utf8mb4",
            autocommit=True,
            ssl=secure_context,
        )

    def _require_connection(self) -> pymysql.connections.Connection:
        if self._connection is None:
            self._connection = self._open_connection()
        return self._connection

    @staticmethod
    def _format_updated_at(updated_at: datetime | None, *, treat_as_text: bool) -> datetime | str | None:
        if updated_at is None:
            return None
        if not treat_as_text:
            return updated_at
        return updated_at.replace(microsecond=0).isoformat()

    @staticmethod
    def _build_customer(
        row: dict[str, Any],
        contacts: list[repairshopr_models.Contact],
    ) -> repairshopr_models.Customer:
        customer_id = _require_int(row.get("id"), field_name="customer.id")
        return repairshopr_models.Customer(
            id=customer_id,
            firstname=_to_text(row.get("firstname")),
            lastname=_to_text(row.get("lastname")),
            fullname=_to_text(row.get("fullname")),
            business_name=_to_text(row.get("business_name")),
            email=_to_text(row.get("email")),
            phone=_to_text(row.get("phone")),
            mobile=_to_text(row.get("mobile")),
            address=_to_text(row.get("address")),
            address_2=_to_text(row.get("address_2")),
            city=_to_text(row.get("city")),
            state=_to_text(row.get("state")),
            zip=_to_text(row.get("zip")),
            notes=_to_text(row.get("notes")),
            disabled=row.get("disabled"),
            no_email=row.get("no_email"),
            contacts=contacts,
        )

    @staticmethod
    def _build_contact(row: dict[str, Any]) -> repairshopr_models.Contact:
        contact_id = _require_int(row.get("id"), field_name="contact.id")
        return repairshopr_models.Contact(
            id=contact_id,
            name=_to_text(row.get("name")),
            address1=_to_text(row.get("address1")),
            address2=_to_text(row.get("address2")),
            city=_to_text(row.get("city")),
            state=_to_text(row.get("state")),
            zip=_to_text(row.get("zip")),
            email=_to_text(row.get("email")),
            phone=_to_text(row.get("phone")),
            mobile=_to_text(row.get("mobile")),
            notes=_to_text(row.get("notes")),
            extension=_to_text(row.get("extension")),
            processed_phone=_to_text(row.get("processed_phone")),
            processed_mobile=_to_text(row.get("processed_mobile")),
        )

    @staticmethod
    def _build_product(row: dict[str, Any]) -> repairshopr_models.Product:
        product_id = _require_int(row.get("id"), field_name="product.id")
        return repairshopr_models.Product(
            id=product_id,
            price_cost=_to_float(row.get("price_cost")),
            price_retail=_to_float(row.get("price_retail")),
            description=_to_text(row.get("description")),
            name=_to_text(row.get("name")),
            disabled=row.get("disabled"),
            product_category=_to_text(row.get("product_category")),
            category_path=_to_text(row.get("category_path")),
            upc_code=_to_text(row.get("upc_code")),
            long_description=_to_text(row.get("long_description")),
        )

    @staticmethod
    def _build_ticket_properties(row: dict[str, Any]) -> repairshopr_models.TicketProperties:
        return repairshopr_models.TicketProperties(
            id=row.get("id"),
            day=_to_text(row.get("day")),
            case=_to_text(row.get("case")),
            other=_to_text(row.get("other")),
            s_n_num=_to_text(row.get("s_n_num")),
            tag_num=_to_text(row.get("tag_num")),
            claim_num=_to_text(row.get("claim_num")),
            location=_to_text(row.get("location")),
            transport=_to_text(row.get("transport")),
            boces=_to_text(row.get("boces")),
            tag_num_2=_to_text(row.get("tag_num_2")),
            delivery_num=_to_text(row.get("delivery_num")),
            transport_2=_to_text(row.get("transport_2")),
            po_num_2=_to_text(row.get("po_num_2")),
            phone_num=_to_text(row.get("phone_num")),
            p_g_name=_to_text(row.get("p_g_name")),
            student=_to_text(row.get("student")),
            s_n=_to_text(row.get("s_n")),
            drop_off_location=_to_text(row.get("drop_off_location")),
            call_num=_to_text(row.get("call_num")),
        )

    @staticmethod
    def _build_ticket_comment(row: dict[str, Any]) -> repairshopr_models.TicketComment:
        comment_id = _require_int(row.get("id"), field_name="ticket_comment.id")
        return repairshopr_models.TicketComment(
            id=comment_id,
            created_at=_to_datetime(row.get("created_at")),
            subject=_to_text(row.get("subject")),
            body=_to_text(row.get("body")),
            tech=_to_text(row.get("tech")),
            hidden=row.get("hidden"),
        )

    @staticmethod
    def _build_ticket(
        row: dict[str, Any],
        properties: repairshopr_models.TicketProperties,
        comments: list[repairshopr_models.TicketComment],
    ) -> repairshopr_models.Ticket:
        ticket_id = _require_int(row.get("id"), field_name="ticket.id")
        return repairshopr_models.Ticket(
            id=ticket_id,
            number=row.get("number"),
            subject=_to_text(row.get("subject")),
            created_at=_to_datetime(row.get("created_at")),
            customer_id=row.get("customer_id"),
            customer_business_then_name=_to_text(row.get("customer_business_then_name")),
            problem_type=_to_text(row.get("problem_type")),
            status=_to_text(row.get("status")),
            priority=_to_text(row.get("priority")),
            properties=properties,
            comments=comments,
        )

    @staticmethod
    def _build_estimate(row: dict[str, Any]) -> repairshopr_models.Estimate:
        estimate_id = _require_int(row.get("id"), field_name="estimate.id")
        return repairshopr_models.Estimate(
            id=estimate_id,
            customer_id=row.get("customer_id"),
            customer_business_then_name=_to_text(row.get("customer_business_then_name")),
            number=_to_text(row.get("number")),
            created_at=_to_datetime(row.get("created_at")),
            date=_to_datetime(row.get("date")),
            employee=_to_text(row.get("employee")),
        )

    @staticmethod
    def _build_invoice(row: dict[str, Any]) -> repairshopr_models.Invoice:
        invoice_id = _require_int(row.get("id"), field_name="invoice.id")
        return repairshopr_models.Invoice(
            id=invoice_id,
            customer_id=row.get("customer_id"),
            customer_business_then_name=_to_text(row.get("customer_business_then_name")),
            number=_to_text(row.get("number")),
            created_at=_to_datetime(row.get("created_at")),
            date=_to_datetime(row.get("date")),
            due_date=_to_datetime(row.get("due_date")),
            note=_to_text(row.get("note")),
        )

    @staticmethod
    def _build_line_item(row: dict[str, Any]) -> dict[str, object]:
        return {
            "id": row.get("id"),
            "product_id": row.get("product_id"),
            "item": row.get("item"),
            "name": row.get("name"),
            "price": row.get("price"),
            "quantity": row.get("quantity"),
            "discount_percent": row.get("discount_percent"),
        }


def chunk_values(values: Iterable[int], batch_size: int) -> Iterator[list[int]]:
    batch: list[int] = []
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _require_int(value: object, *, field_name: str) -> int:
    parsed_value = _to_int(value)
    if parsed_value is None:
        raise ValueError(f"Missing {field_name} value")
    return parsed_value


def _to_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return None
