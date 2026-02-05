import logging
import re
from datetime import datetime, UTC
from enum import StrEnum
from typing import TypeVar, Self, Protocol, Iterable

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
from psycopg2.errors import UniqueViolation

from .gql.base_model import BaseModel


T = TypeVar("T")


class OdooRecordInfo(Protocol):
    id: int | None
    name: str | None
    default_code: str | None

_logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 30
DEFAULT_DATETIME = datetime(2000, 1, 1)
SHOPIFY_PAGE_SIZE = 250
COMMIT_SIZE = SHOPIFY_PAGE_SIZE // 10
ADDRESS_RESOURCE_DEFAULT = "address"
ADDRESS_RESOURCE_INVOICE = "address_invoice"
ADDRESS_RESOURCE_DELIVERY = "address_delivery"
PUBLICATION_CHANNELS: dict[str, int] = {
    "online_store": 19453116480,
    "pos": 42683596853,
    "google": 88268636213,
    "shop": 99113467957,
}

_DIGIT_PATTERN = re.compile(r"\D+")


def normalize_str(value: str | None) -> str:
    return (value or "").strip().casefold()


def normalize_phone(value: str | None) -> str:
    return _DIGIT_PATTERN.sub("", value or "")


def normalize_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def shopify_address_resource_for_role(role: str | None) -> str:
    if role == "billing":
        return ADDRESS_RESOURCE_INVOICE
    if role == "shipping":
        return ADDRESS_RESOURCE_DELIVERY
    return ADDRESS_RESOURCE_DEFAULT


def shopify_address_resources_for_role(role: str | None) -> list[str]:
    if role == "billing":
        return [ADDRESS_RESOURCE_INVOICE, ADDRESS_RESOURCE_DEFAULT, ADDRESS_RESOURCE_DELIVERY]
    if role == "shipping":
        return [ADDRESS_RESOURCE_DELIVERY, ADDRESS_RESOURCE_DEFAULT, ADDRESS_RESOURCE_INVOICE]
    return [ADDRESS_RESOURCE_INVOICE, ADDRESS_RESOURCE_DELIVERY, ADDRESS_RESOURCE_DEFAULT]


def find_partner_by_shopify_address_id(
    env: api.Environment,
    shopify_address_id: str,
    *,
    role: str | None = None,
) -> "odoo.model.res_partner":
    address_resources = shopify_address_resources_for_role(role)
    partner_model: "odoo.model.res_partner" = env["res.partner"]
    if not shopify_address_id or not address_resources:
        return partner_model.browse()
    for resource in address_resources:
        address_map = map_records_by_external_ids(
            env,
            model_name="res.partner",
            system_code="shopify",
            resource=resource,
            external_ids=[shopify_address_id],
        )
        partner_record = address_map.get(shopify_address_id)
        if partner_record and partner_record.exists():
            return partner_model.browse(partner_record.id)
    return partner_model.browse()


def image_order_key(image: "odoo.model.product_image") -> tuple[int, datetime]:
    return image.sequence or 0, image.create_date or DEFAULT_DATETIME


def last_import_config_key(resource_type: str) -> str:
    return f"shopify.last_{resource_type}_import_time"


class SyncMode(StrEnum):
    def __new__(cls, value: str, resource_type: str | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._resource_type = resource_type
        return obj

    IMPORT_THEN_EXPORT_PRODUCTS = ("import_then_export_products", "product")
    IMPORT_CHANGED_PRODUCTS = ("import_changed_products", "product")
    EXPORT_CHANGED_PRODUCTS = ("export_changed_products", "product")
    IMPORT_ALL_PRODUCTS = ("import_all_products", "product")
    EXPORT_ALL_PRODUCTS = ("export_all_products", "product")
    IMPORT_PRODUCTS_SINCE_DATE = ("import_products_since_date", "product")
    EXPORT_PRODUCTS_SINCE_DATE = ("export_products_since_date", "product")
    IMPORT_ONE_PRODUCT = ("import_one_product", None)
    EXPORT_BATCH_PRODUCTS = ("export_batch_products", None)

    IMPORT_ALL_ORDERS = ("import_all_orders", "order")
    IMPORT_CHANGED_ORDERS = ("import_changed_orders", "order")
    IMPORT_ONE_ORDER = ("import_one_order", None)

    IMPORT_ALL_CUSTOMERS = ("import_all_customers", "customer")
    IMPORT_CHANGED_CUSTOMERS = ("import_changed_customers", "customer")
    IMPORT_ONE_CUSTOMER = ("import_one_customer", None)

    RESET_SHOPIFY = ("reset_shopify", None)

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()

    @property
    def resource_type(self) -> str | None:
        return self._resource_type

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(m.value, m.display_name) for m in cls]


class OdooDataError(UserError):
    def __init__(self, message: str, odoo_record: models.Model | OdooRecordInfo | None = None) -> None:
        super().__init__(message)
        self.odoo_record = odoo_record

    @property
    def sku(self) -> str:
        if self.odoo_record:
            return getattr(self.odoo_record, "default_code", "")
        return ""

    @property
    def odoo_product_id(self) -> str:
        if self.odoo_record:
            record_id = getattr(self.odoo_record, "id", None)
            return str(record_id) if record_id is not None else ""
        return ""

    @property
    def name(self) -> str:
        if self.odoo_record:
            return getattr(self.odoo_record, "name", "")
        return ""

    def __str__(self) -> str:
        text = super().__str__()
        if self.name:
            text += f" [Odoo Name {self.name}]"
        if self.odoo_product_id:
            text += f" [Odoo ID {self.odoo_product_id}]"
        if self.sku:
            text += f" [Odoo SKU {self.sku}]"
        return text


class OdooMissingSkuError(OdooDataError):
    pass


class ShopifySyncRunFailed(Exception):
    pass


class ShopifySyncCanceled(Exception):
    pass


class ShopifyApiError(OdooDataError):
    def __init__(
        self,
        message: str,
        *,
        shopify_record: BaseModel | None = None,
        shopify_input: BaseModel | None = None,
        odoo_record: models.Model | OdooRecordInfo | None = None,
    ) -> None:
        super().__init__(message, odoo_record=odoo_record)
        self.shopify_record = shopify_record
        self.shopify_input = shopify_input

    def __str__(self) -> str:
        text = super().__str__()
        if not self.odoo_record and self.sku:
            text = text.replace(f" [Odoo SKU {self.sku}]", "")

        if self.__cause__:
            text += f"\nShopify error: {self.__cause__}"

        if not self.shopify_record:
            return text

        if self.name and self.name not in text:
            text += f" [{self.name}]"
        if self.shopify_product_id:
            text += f" [Shopify ID {self.shopify_product_id}]"
        if self.sku and f"[Shopify SKU {self.sku}]" not in text:
            text += f" [Shopify SKU {self.sku}]"
        return text

    @property
    def sku(self) -> str:
        record = self.shopify_record
        if not record:
            return ""
        variants = getattr(record, "variants", None)
        nodes = getattr(variants, "nodes", None) if variants else None
        if not nodes:
            return ""
        try:
            return nodes[0].sku or ""
        except (AttributeError, IndexError, TypeError):
            return ""

    @property
    def shopify_product_id(self) -> str:
        if self.shopify_record:
            return getattr(self.shopify_record, "id", "")
        return ""

    @property
    def name(self) -> str:
        if self.shopify_record:
            return getattr(self.shopify_record, "title", "")
        return super().name


class ShopifyDataError(ShopifyApiError):
    pass


class ShopifyMissingSkuFieldError(ShopifyDataError):
    pass


class ShopifyStaleRunTimeout(Exception):
    pass


def write_if_changed(
    record: "odoo.model.product_product | odoo.model.product_template | odoo.model.sale_order | odoo.model.sale_order_line | odoo.model.res_partner",
    vals: "odoo.values.product_product | odoo.values.product_template | odoo.values.sale_order | odoo.values.sale_order_line | odoo.values.res_partner",
) -> bool:
    remaining_values = vals.copy()

    for field_name, new_value in list(remaining_values.items()):
        current_value = record[field_name]
        field = record._fields[field_name]

        if isinstance(new_value, (list, tuple)):
            raise UserError(f"write_if_changed(): unsupported value for field '{field_name}'. lists and tuples are not supported.")
        if isinstance(current_value, models.BaseModel):
            if len(current_value) > 1:
                raise UserError(
                    f"write_if_changed(): field '{field_name}' contains a multi‑record recordset which is not supported."
                )
            current_id = current_value.id if current_value else False
            new_id = new_value.id if isinstance(new_value, models.BaseModel) else new_value
            if current_id == new_id:
                remaining_values.pop(field_name)
            continue
        if isinstance(current_value, float):
            digits_specification = getattr(field, "digits", None)
            raw_digits = digits_specification(record.env) if callable(digits_specification) else digits_specification
            precision_digits = raw_digits[1] if isinstance(raw_digits, (list, tuple)) and len(raw_digits) > 1 else 2
            if float_compare(current_value, new_value, precision_digits=precision_digits) == 0:
                remaining_values.pop(field_name)
            continue
        if current_value == new_value:
            remaining_values.pop(field_name)

    if remaining_values:
        record.with_context(skip_shopify_sync=True, force_sku_check=True).write(remaining_values)

    return bool(remaining_values)


def parse_shopify_datetime_to_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)


def format_datetime_for_shopify(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_shopify_id_from_gid(gid: str) -> str:
    if isinstance(gid, int):
        return str(gid)
    segment = gid.split("/")[-1]
    if "?" in segment:
        segment = segment.split("?", 1)[0]
    return segment


def format_shopify_gid_from_id(resource_type: str, resource_id: int | str) -> str:
    return f"gid://shopify/{resource_type}/{resource_id}"


def upsert_external_id(
    record: models.Model,
    *,
    system_code: str,
    resource: str,
    external_id_value: str | None,
) -> None:
    system = record.env["external.system"].search([("code", "=", system_code)], limit=1)
    if not system:
        return

    external_id_model = record.env["external.id"].sudo()
    external_id_model_all = external_id_model.with_context(active_test=False)
    existing = external_id_model_all.search(
        [
            ("res_model", "=", record._name),
            ("res_id", "=", record.id),
            ("system_id", "=", system.id),
            ("resource", "=", resource),
        ],
        limit=1,
    )
    sanitized = (external_id_value or "").strip()
    if sanitized:
        conflicting = external_id_model_all.search(
            [
                ("system_id", "=", system.id),
                ("resource", "=", resource),
                ("external_id", "=", sanitized),
            ],
            limit=1,
        )
        if conflicting and conflicting.res_model == record._name:
            if existing and existing.id != conflicting.id:
                existing.unlink()
            if conflicting.res_id != record.id or not conflicting.active:
                conflicting.write(
                    {
                        "res_model": record._name,
                        "res_id": record.id,
                        "active": True,
                    }
                )
            return
        if conflicting and conflicting.res_model != record._name:
            _logger.warning(
                "Skipping external ID %s for %s(%s): already used by %s(%s).",
                sanitized,
                record._name,
                record.id,
                conflicting.res_model,
                conflicting.res_id,
            )
            return
        if existing:
            existing.write({"external_id": sanitized, "active": True})
        else:
            try:
                with record.env.cr.savepoint():
                    external_id_model.create(
                        {
                            "res_model": record._name,
                            "res_id": record.id,
                            "system_id": system.id,
                            "resource": resource,
                            "external_id": sanitized,
                            "active": True,
                        }
                    )
            except UniqueViolation:
                existing_after_conflict = external_id_model_all.search(
                    [
                        ("res_model", "=", record._name),
                        ("res_id", "=", record.id),
                        ("system_id", "=", system.id),
                        ("resource", "=", resource),
                    ],
                    limit=1,
                )
                if existing_after_conflict:
                    update_values = {}
                    if existing_after_conflict.external_id != sanitized:
                        update_values["external_id"] = sanitized
                    if not existing_after_conflict.active:
                        update_values["active"] = True
                    if update_values:
                        existing_after_conflict.write(update_values)
                    return
                conflicting_after_conflict = external_id_model_all.search(
                    [
                        ("system_id", "=", system.id),
                        ("resource", "=", resource),
                        ("external_id", "=", sanitized),
                    ],
                    limit=1,
                )
                if not conflicting_after_conflict:
                    raise
                if conflicting_after_conflict.res_model == record._name:
                    if (
                        conflicting_after_conflict.res_id != record.id
                        or not conflicting_after_conflict.active
                    ):
                        conflicting_after_conflict.write(
                            {
                                "res_model": record._name,
                                "res_id": record.id,
                                "active": True,
                            }
                        )
                else:
                    _logger.warning(
                        "Skipping external ID %s for %s(%s): already used by %s(%s).",
                        sanitized,
                        record._name,
                        record.id,
                        conflicting_after_conflict.res_model,
                        conflicting_after_conflict.res_id,
                    )
                    return
        return

    if existing:
        existing.write({"active": False})


def map_records_by_external_ids(
    env: api.Environment,
    *,
    model_name: str,
    system_code: str,
    resource: str,
    external_ids: Iterable[str],
) -> dict[str, models.Model]:
    external_id_values = [value for value in external_ids if value]
    if not external_id_values:
        return {}

    system = env["external.system"].search([("code", "=", system_code)], limit=1)
    if not system:
        return {}

    external_id_model = env["external.id"].sudo()
    external_id_records = external_id_model.search(
        [
            ("system_id", "=", system.id),
            ("resource", "=", resource),
            ("external_id", "in", list(set(external_id_values))),
            ("res_model", "=", model_name),
            ("active", "=", True),
        ]
    )

    record_model = env[model_name]
    mapped: dict[str, models.Model] = {}
    for external_id_record in external_id_records:
        mapped[external_id_record.external_id] = record_model.browse(external_id_record.res_id)
    return mapped


def find_record_by_external_id(
    env: api.Environment,
    *,
    model_name: str,
    system_code: str,
    resource: str,
    external_id_value: str | None,
) -> models.Model:
    sanitized = (external_id_value or "").strip()
    if not sanitized:
        return env[model_name].browse()
    records = map_records_by_external_ids(
        env,
        model_name=model_name,
        system_code=system_code,
        resource=resource,
        external_ids=[sanitized],
    )
    record = records.get(sanitized)
    return record if record and record.exists() else env[model_name].browse()


def parse_shopify_sku_field_to_sku_and_bin(sku_field: str) -> tuple[str, str]:
    if not sku_field or not sku_field.strip():
        raise ShopifyMissingSkuFieldError("No SKU field from Shopify")

    sku_field_separator = " - " if " - " in sku_field else " "
    parts = [value.strip() for value in sku_field.split(sku_field_separator, 1)]

    sku = parts[0]
    bin_location = parts[1] if len(parts) > 1 else ""

    if not sku:
        raise ShopifyMissingSkuFieldError("No SKU from Shopify")

    return sku, bin_location


def format_sku_bin_for_shopify(sku: str | None, bin_location: str | None) -> str:
    if sku is None or sku.strip() == "":
        raise OdooMissingSkuError("No SKU to format for Shopify")
    sku = sku.strip()

    bin_location = (bin_location or "").strip()
    return f"{sku} - {bin_location}"


def determine_latest_odoo_product_modification_time(product: "odoo.model.product_product") -> datetime:
    dates = [
        product.write_date,
        product.product_tmpl_id.write_date,
        product.shopify_last_exported_at,
        DEFAULT_DATETIME,
    ]
    return max(filter(None, dates))


def get_latest_image_write_date(product: "odoo.model.product_product") -> datetime:
    image_records = product.images
    if not image_records:
        return DEFAULT_DATETIME
    image_dates = [image.write_date for image in image_records if image.write_date]
    return max(image_dates) if image_dates else DEFAULT_DATETIME
