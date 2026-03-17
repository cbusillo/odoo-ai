from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

POLL_SECONDS = 5
SYNC_TIMEOUT_SECONDS = 8 * 60 * 60
TITLE_TIMEOUT_SECONDS = 180
FIELD_TIMEOUT_SECONDS = 180
SYNC_SEARCH_CUTOFF_SECONDS = 300
SYNC_SETTLE_TIMEOUT_SECONDS = 300
SYNC_SETTLE_QUIET_SECONDS = 15
DEFAULT_REMOTE_LOGIN = "gpt-admin"
SUPPORTED_REMOTE_INSTANCES = ("dev", "testing", "prod")
VALIDATION_PROFILES = ("smoke", "full")
DEFAULT_SAMPLE_SIZE = 25
VALIDATION_EXPORT_MARKER_OFFSET_SECONDS = 60 * 60
SHOPIFY_WEBHOOK_PAUSE_KEY = "shopify.pause_webhook_processing"
SHOPIFY_AUTOSCHEDULE_PAUSE_KEY = "shopify.pause_sync_autoschedule"
PREPARE_SYNC_MODES = (
    "reset_shopify",
    "export_all_products",
    "import_then_export_products",
    "export_changed_products",
    "export_batch_products",
)
ROUNDTRIP_SYNC_MODES = ("import_then_export_products", "export_changed_products", "import_one_product", "export_batch_products")
SHOPIFY_METAFIELD_NAMESPACE = "custom"
CONDITION_METAFIELD_KEY = "condition"
CONFLICTING_SYNC_STATES = ("queued", "running")
CONFLICT_CLEAR_MAX_RETRIES = 5
CONFLICT_CLEAR_RETRY_SLEEP_SECONDS = 1.0
ZERO_DECIMAL = Decimal(0)


@dataclass(frozen=True)
class RemoteShopifySettings:
    odoo_url: str
    database_name: str
    odoo_password: str
    remote_login: str
    shop_url_key: str
    shopify_api_token: str
    shopify_api_version: str


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: int
    title: str
    description_html: str
    condition_id: int | None
    condition_code: str | None
    list_price: Decimal = ZERO_DECIMAL
    standard_price: Decimal = ZERO_DECIMAL
    quantity_available: float = 0.0
    image_count: int = 0


@dataclass(frozen=True)
class ShopifyProductSnapshot:
    title: str | None
    description_html: str | None
    condition_metafield_id: str | None
    condition_code: str | None
    status: str | None = None
    total_inventory: int | None = None
    variant_price: Decimal | None = None
    variant_unit_cost: Decimal | None = None
    media_count: int = 0
    failed_media_count: int = 0


@dataclass(frozen=True)
class RoundtripProductSelection:
    product_snapshot: ProductSnapshot
    shopify_product_id: str
    export_product_ids: tuple[int, ...]


@dataclass(frozen=True)
class RoundtripPrepareSelection:
    product_snapshot: ProductSnapshot
    export_product_ids: tuple[int, ...]


def _normalize_html_fragment(value: str | None) -> str:
    return html.unescape(value or "")


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    return int(str(value))


def _snapshot_fields_match(
    *,
    actual_title: str | None,
    actual_description_html: str | None,
    actual_condition_code: str | None,
    expected_title: str | None,
    expected_description_html: str | None,
    expected_condition_code: str | None,
) -> bool:
    if expected_title is not None and actual_title != expected_title:
        return False
    normalized_expected_description = _normalize_html_fragment(expected_description_html)
    normalized_actual_description = _normalize_html_fragment(actual_description_html)
    if expected_description_html is not None and normalized_actual_description != normalized_expected_description:
        return False
    if expected_condition_code is not None and actual_condition_code != expected_condition_code:
        return False
    return True


def _expected_shopify_status(product_snapshot: ProductSnapshot) -> str:
    return "ACTIVE" if product_snapshot.quantity_available > 0 else "DRAFT"


def _shopify_prepare_snapshot_matches(*, actual_snapshot: ShopifyProductSnapshot, product_snapshot: ProductSnapshot) -> bool:
    if actual_snapshot.status != _expected_shopify_status(product_snapshot):
        return False
    if actual_snapshot.total_inventory != int(product_snapshot.quantity_available):
        return False
    if actual_snapshot.variant_price != product_snapshot.list_price:
        return False
    if actual_snapshot.variant_unit_cost != product_snapshot.standard_price:
        return False
    if product_snapshot.image_count > 0 and actual_snapshot.media_count < product_snapshot.image_count:
        return False
    if actual_snapshot.failed_media_count:
        return False
    return True


def _parse_odoo_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _future_utc_timestamp(offset_seconds: int) -> str:
    return (datetime.now(tz=UTC) + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")
