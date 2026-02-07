from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Contact:
    id: int
    name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    notes: str | None = None
    extension: str | None = None
    processed_phone: str | None = None
    processed_mobile: str | None = None


@dataclass
class Customer:
    id: int
    firstname: str | None = None
    lastname: str | None = None
    fullname: str | None = None
    business_name: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    address: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    notes: str | None = None
    disabled: bool | None = None
    no_email: bool | None = None
    updated_at: datetime | None = None
    contacts: list[Contact] = field(default_factory=list)


# noinspection DuplicatedCode
# Schema mirrors sync DB columns; field repetition is intentional.
@dataclass
class Product:
    id: int
    price_cost: float | None = None
    price_retail: float | None = None
    description: str | None = None
    name: str | None = None
    disabled: bool | None = None
    product_category: str | None = None
    category_path: str | None = None
    upc_code: str | None = None
    long_description: str | None = None
    updated_at: datetime | None = None


@dataclass
class TicketProperties:
    id: int | None = None
    day: str | None = None
    case: str | None = None
    other: str | None = None
    s_n_num: str | None = None
    tag_num: str | None = None
    claim_num: str | None = None
    location: str | None = None
    transport: str | None = None
    boces: str | None = None
    tag_num_2: str | None = None
    delivery_num: str | None = None
    transport_2: str | None = None
    po_num_2: str | None = None
    phone_num: str | None = None
    p_g_name: str | None = None
    student: str | None = None
    s_n: str | None = None
    drop_off_location: str | None = None
    call_num: str | None = None


@dataclass
class TicketComment:
    id: int
    created_at: datetime | None = None
    subject: str | None = None
    body: str | None = None
    tech: str | None = None
    hidden: bool | None = None


@dataclass
class Ticket:
    id: int
    number: int | None = None
    subject: str | None = None
    created_at: datetime | None = None
    customer_id: int | None = None
    customer_business_then_name: str | None = None
    problem_type: str | None = None
    status: str | None = None
    priority: str | None = None
    updated_at: datetime | None = None
    properties: TicketProperties = field(default_factory=TicketProperties)
    comments: list[TicketComment] = field(default_factory=list)


@dataclass
class SalesDocument:
    id: int
    customer_id: int | None = None
    customer_business_then_name: str | None = None
    number: str | None = None
    created_at: datetime | None = None
    date: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Estimate(SalesDocument):
    employee: str | None = None
    ticket_id: int | None = None


@dataclass
class Invoice(SalesDocument):
    due_date: datetime | None = None
    note: str | None = None
    ticket_id: int | None = None
