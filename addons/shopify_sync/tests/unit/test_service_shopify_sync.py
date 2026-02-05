from ..common_imports import timedelta, MagicMock, tagged, UNIT_TAGS
from odoo.api import Environment

from ...services.shopify.sync.base import ShopifyBaseImporter, ShopifyBaseExporter, ShopifyBaseDeleter
from ...services.shopify.helpers import format_datetime_for_shopify, parse_shopify_datetime_to_utc
from ...services.shopify.gql import Client
from ..fixtures.base import UnitTestCase


class DummySync:
    def __init__(self) -> None:
        self.id = 1
        self.hard_throttle_count = 0
        self.total_count = 0
        self.updated_count = 0

    def ensure_not_canceled(self) -> None:
        return


class DummyPageInfo:
    def __init__(self, cursor: str | None = None, has_next: bool = False) -> None:
        self.end_cursor = cursor
        self.has_next_page = has_next


class DummyPage:
    def __init__(self, nodes: list[int], cursor: str | None = None, has_next: bool = False) -> None:
        self.nodes = nodes
        self.page_info = DummyPageInfo(cursor, has_next)


class DummyImporter(ShopifyBaseImporter[int]):
    def __init__(self, env: Environment, sync_record: DummySync, pages: list[DummyPage]) -> None:
        super().__init__(env, sync_record)
        self.pages = pages
        self.fetch_calls: list[tuple[str | None, str | None]] = []
        self.imported: list[int] = []
        self.run_query: str | None = None
        self.service = MagicMock()
        self.service.client = MagicMock()

    def _fetch_page(self, client: Client, query: str | None, cursor: str | None) -> DummyPage:
        index = len(self.fetch_calls)
        self.fetch_calls.append((query, cursor))
        return self.pages[index] if index < len(self.pages) else DummyPage([])

    def _import_one(self, node: int) -> bool:
        self.imported.append(node)
        return node % 2 == 0

    def run(self, *, query: str | None = None) -> None:
        self.run_query = query
        super().run(query=query)


class DummyExporter(ShopifyBaseExporter[int]):
    def __init__(self, env: Environment, sync_record: DummySync) -> None:
        super().__init__(env, sync_record)
        self.exported: list[int] = []
        self.service = MagicMock()
        self.service.client = MagicMock()

    def _export_one(self, record: int) -> None:
        self.exported.append(record)


class DummyDeleter(ShopifyBaseDeleter[int]):
    def __init__(self, env: Environment, sync_record: DummySync) -> None:
        super().__init__(env, sync_record)
        self.deleted: list[int] = []
        self.service = MagicMock()
        self.service.client = MagicMock()

    def _delete_one(self, record: int) -> None:
        self.deleted.append(record)


def make_pages() -> list[DummyPage]:
    return [DummyPage([1, 2], "c1", True), DummyPage([3, 4])]


@tagged(*UNIT_TAGS)
class TestShopifySyncItems(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("shopify.shop_url_key", "dummy.example.com")
        config.set_param("shopify.api_token", "dummy_token")

    @staticmethod
    def _sync() -> DummySync:
        return DummySync()

    def test_importer_iterates_pages(self) -> None:
        sync = self._sync()
        importer = DummyImporter(self.env, sync, make_pages())
        importer.run(query="test")
        self.assertEqual(importer.fetch_calls, [("test", None), ("test", "c1")])
        self.assertEqual(importer.imported, [1, 2, 3, 4])
        self.assertEqual(sync.total_count, 4)
        self.assertEqual(sync.updated_count, 2)

    def test_importer_run_by_id(self) -> None:
        sync = self._sync()
        importer = DummyImporter(self.env, sync, make_pages())
        self.assertTrue(importer.run_by_id(42))
        self.assertEqual(importer.run_query, 'id:"42"')

    def test_importer_run_since_last_import(self) -> None:
        sync = self._sync()
        key = "shopify.last_order_import_time"
        time_string = "2024-01-01T12:00:00Z"
        self.env["ir.config_parameter"].set_param(key, time_string)
        importer = DummyImporter(self.env, sync, make_pages())
        importer.run_since_last_import("order")
        expected_time = parse_shopify_datetime_to_utc(time_string) - timedelta(seconds=2)
        expected_filter = f'updated_at:>"{format_datetime_for_shopify(expected_time)}"'
        self.assertEqual(importer.run_query, expected_filter)

    def test_exporter_run(self) -> None:
        sync = self._sync()
        exporter = DummyExporter(self.env, sync)
        exporter.run([1, 2, 3])
        self.assertEqual(exporter.exported, [1, 2, 3])
        self.assertEqual(sync.total_count, 3)
        self.assertEqual(sync.updated_count, 3)

    def test_exporter_run_empty(self) -> None:
        sync = self._sync()
        exporter = DummyExporter(self.env, sync)
        exporter.run([])
        self.assertEqual(exporter.exported, [])
        self.assertEqual(sync.total_count, 0)

    def test_deleter_collect_nodes_and_run(self) -> None:
        sync = self._sync()
        deleter = DummyDeleter(self.env, sync)

        pages = [DummyPage([1], "c1", True), DummyPage([2])]

        def fetch_page(_query: str, cursor: str) -> DummyPage:
            return pages[0] if cursor is None else pages[1]

        nodes = deleter.collect_nodes(fetch_page, query="test")
        self.assertEqual(nodes, [1, 2])
        deleter.run(nodes)
        self.assertEqual(deleter.deleted, [1, 2])
        self.assertEqual(sync.updated_count, 2)
        self.assertEqual(sync.total_count, 2)

    def test_deleter_run_empty(self) -> None:
        sync = self._sync()
        deleter = DummyDeleter(self.env, sync)
        deleter.run([])
        self.assertEqual(deleter.deleted, [])
        self.assertEqual(sync.total_count, 0)
