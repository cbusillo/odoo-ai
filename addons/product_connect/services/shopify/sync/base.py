import logging, time
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Generic, TypeVar, Sequence, Callable, Protocol

import psycopg2
from odoo.api import Environment

from ..gql import Client
from ..service import ShopifyService
from ..helpers import (
    OdooDataError,
    ShopifyDataError,
    COMMIT_SIZE,
    SHOPIFY_PAGE_SIZE,
    HEARTBEAT_SECONDS,
    DEFAULT_DATETIME,
    ShopifyApiError,
    parse_shopify_datetime_to_utc,
    format_datetime_for_shopify,
    last_import_config_key,
)

_logger = logging.getLogger(__name__)

T = TypeVar("T")


class _PageInfo(Protocol):
    end_cursor: str | None
    has_next_page: bool


class ShopifyPage(Protocol[T]):
    nodes: Sequence[T]
    page_info: _PageInfo


class ShopifyBase(ABC, Generic[T]):
    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        self.env = env
        self.sync_record = sync_record
        self.service = ShopifyService(env, sync_record)
        self._last_heartbeat = time.monotonic()
        self.page_size = SHOPIFY_PAGE_SIZE
        self.commit_size = COMMIT_SIZE
        self.default_datetime = DEFAULT_DATETIME

    def _maybe_commit(self, processed_count: int) -> None:
        if processed_count % self.commit_size == 0:
            try:
                self.sync_record._safe_commit()
                _logger.info(f"Processed {processed_count} records so far.")
            except psycopg2.errors.SerializationFailure:
                _logger.warning(f"Commit at {processed_count} records skipped due to concurrent access")
                self.sync_record._safe_rollback()
                raise
        if time.monotonic() - self._last_heartbeat > HEARTBEAT_SECONDS:
            try:
                self.sync_record.write({})
                self.sync_record._safe_commit()
            except psycopg2.errors.SerializationFailure:
                _logger.warning("Heartbeat update skipped due to concurrent access")
                self.sync_record._safe_rollback()
            self._last_heartbeat = time.monotonic()

    def _iterate_pages(
        self,
        fetch_page: Callable[[str | None, str | None], ShopifyPage[T]],
        process_one: Callable[[T], bool],
        query: str | None = None,
    ) -> None:
        cursor: str | None = None
        has_next = True
        total_processed = 0
        while has_next:
            page = fetch_page(query, cursor)
            nodes = page.nodes
            if not nodes:
                break

            self.sync_record.total_count += len(nodes)

            for node in nodes:
                total_processed += 1

                try:
                    if process_one(node):
                        self.sync_record.updated_count += 1
                except (OdooDataError, ShopifyDataError):
                    raise
                except Exception as error:
                    raise ShopifyDataError("unexpected error", shopify_record=node) from error
                self._maybe_commit(total_processed)

            cursor = page.page_info.end_cursor
            has_next = page.page_info.has_next_page


class ShopifyBaseImporter(ShopifyBase[T]):
    def run(self, *, query: str | None = None) -> None:
        def fetch_page(query_string: str | None, cursor_string: str | None) -> ShopifyPage[T]:
            return self._fetch_page(self.service.client, query_string, cursor_string)

        self._iterate_pages(fetch_page, self._import_one, query)

    @abstractmethod
    def _fetch_page(self, client: Client, query: str | None, cursor: str | None) -> ShopifyPage[T]: ...

    def run_since_last_import(self, config_key_type: str, *, time_shift_seconds: int = 2) -> int:
        config_key = last_import_config_key(config_key_type)
        param = self.env["ir.config_parameter"].get_param(config_key)
        last_time = parse_shopify_datetime_to_utc(param) if param else self.default_datetime
        filter_query = f'updated_at:>"{format_datetime_for_shopify(last_time - timedelta(seconds=time_shift_seconds))}"'
        self.run(query=filter_query)
        return self.sync_record.updated_count

    def run_by_id(self, resource_id: int | str, *, field: str = "id") -> bool:
        filter_query = f'{field}:"{resource_id}"'
        self.run(query=filter_query)
        return True

    @abstractmethod
    def _import_one(self, node: T) -> bool: ...


class ShopifyBaseExporter(ShopifyBase[T]):
    def run(self, records: Sequence[T]) -> None:
        if not records:
            _logger.info("nothing to export")
            return
        self.sync_record.total_count = self.sync_record.total_count or len(records)
        for index, record in enumerate(records, 1):
            self._export_one(record)
            self.sync_record.updated_count += 1
            self._maybe_commit(index)

    @abstractmethod
    def _export_one(self, record: T) -> None: ...


class ShopifyBaseDeleter(ShopifyBase[T]):
    def collect_nodes(
        self,
        fetch_page: Callable[[str | None, str | None], ShopifyPage[T]],
        query: str | None = None,
    ) -> list[T]:
        nodes: list[T] = []

        def _append(node: T) -> bool:
            nodes.append(node)
            return False  # no “updated” semantics for reads

        self._iterate_pages(fetch_page, _append, query=query)
        _logger.info("Collected %d node(s) for deletion.", len(nodes))
        return nodes

    def run(self, records: Sequence[T]) -> None:
        if not records:
            _logger.info("Nothing to delete")
            return

        self.sync_record.total_count = self.sync_record.total_count or len(records)

        for index, record in enumerate(records, 1):
            try:
                with self.env.cr.savepoint():
                    self._delete_one(record)
            except (OdooDataError, ShopifyApiError):
                raise
            except Exception as error:
                raise ShopifyApiError("unexpected error in deleter", shopify_record=record) from error

            self.sync_record.updated_count += 1
            self._maybe_commit(index)

    @abstractmethod
    def _delete_one(self, record: T) -> None: ...
