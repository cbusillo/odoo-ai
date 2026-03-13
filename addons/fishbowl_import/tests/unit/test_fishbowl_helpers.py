from ...models import fishbowl_rows
from ...models.fishbowl_import_constants import (
    EXTERNAL_SYSTEM_CODE,
    LEGACY_BUCKET_ADHOC,
    LEGACY_BUCKET_DISCOUNT,
    LEGACY_BUCKET_FEE,
    LEGACY_BUCKET_MISC,
    LEGACY_BUCKET_SHIPPING,
)
from ..common_imports import common
from ..fixtures.base import UnitTestCase


class _FetchAllClientStub:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, list[object] | None]] = []

    def fetch_all(self, query: str, params: list[object] | None = None) -> list[dict[str, object]]:
        self.calls.append((query, list(params) if params is not None else None))
        return self._responses.pop(0)


@common.tagged(*common.UNIT_TAGS)
class TestFishbowlHelpers(UnitTestCase):
    def test_to_bool(self) -> None:
        importer_model = self.env["fishbowl.importer"]

        self.assertTrue(importer_model._to_bool("true"))
        self.assertTrue(importer_model._to_bool("1"))
        self.assertFalse(importer_model._to_bool("0"))
        self.assertFalse(importer_model._to_bool(None))
        self.assertTrue(importer_model._to_bool(b"\x01"))
        self.assertFalse(importer_model._to_bool(b"\x00"))

    def test_legacy_bucket_for_line(self) -> None:
        importer_model = self.env["fishbowl.importer"]

        self.assertEqual(importer_model._legacy_bucket_for_line("UPS shipping", 10.0), LEGACY_BUCKET_SHIPPING)
        self.assertEqual(importer_model._legacy_bucket_for_line("handling fee", 5.0), LEGACY_BUCKET_FEE)
        self.assertEqual(importer_model._legacy_bucket_for_line("promo discount", 5.0), LEGACY_BUCKET_DISCOUNT)
        self.assertEqual(importer_model._legacy_bucket_for_line("misc charge", 5.0), LEGACY_BUCKET_MISC)
        self.assertEqual(importer_model._legacy_bucket_for_line("random item", 5.0), LEGACY_BUCKET_ADHOC)
        self.assertEqual(importer_model._legacy_bucket_for_line("discount", -1.0), LEGACY_BUCKET_DISCOUNT)

    def test_legacy_bucket_for_line_non_standard_labels(self) -> None:
        importer_model = self.env["fishbowl.importer"]

        self.assertEqual(importer_model._legacy_bucket_for_line("FedEx freight", 12.0), LEGACY_BUCKET_SHIPPING)
        self.assertEqual(importer_model._legacy_bucket_for_line("Credit card fee", 3.0), LEGACY_BUCKET_FEE)

    def test_build_legacy_line_name(self) -> None:
        importer_model = self.env["fishbowl.importer"]

        line_name = importer_model._build_legacy_line_name("Widget", "SKU-1", None)
        self.assertEqual(line_name, "SKU-1 - Widget")
        line_name = importer_model._build_legacy_line_name("SKU-1 - Widget", "SKU-1", None)
        self.assertEqual(line_name, "SKU-1 - Widget")

    def test_build_legacy_line_name_uses_fallback_product(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        template = self.env["product.template"].create({"name": "Fallback Item"})
        line_name = importer_model._build_legacy_line_name("", "", template.product_variant_id.id)

        self.assertEqual(line_name, template.product_variant_id.display_name)

    def test_product_type_field(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        template_model = self.env["product.template"]
        field_name = importer_model._product_type_field(template_model)
        self.assertIn(field_name, {"detailed_type", "type"})

    def test_get_legacy_bucket_product_id_creates_missing_product(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        product_id = importer_model._get_legacy_bucket_product_id("unknown")
        product = self.env["product.product"].browse(product_id)

        self.assertEqual(product.default_code, "LEGACY-ADHOC")
        self.assertEqual(product.product_tmpl_id.categ_id.name, "Legacy Fishbowl")

    def test_resolve_product_from_sales_row_missing_id(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        row = fishbowl_rows.SalesOrderLineRow(id=1)
        product_maps = {"product": {}}

        product_id = importer_model._resolve_product_from_sales_row(row, product_maps)

        self.assertIsNone(product_id)

    def test_stream_rows_by_ids_yields_parsed_batches(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        client = _FetchAllClientStub(
            [
                [{"id": 10}, {"id": 11}],
                [{"id": 12}],
            ]
        )

        batches = list(
            importer_model._stream_rows_by_ids(
                client,
                "shipitem",
                "shipId",
                [4, 2, 4, 1],
                select_columns="id",
                batch_size=2,
                row_parser=fishbowl_rows.SHIPMENT_LINE_ROWS_ADAPTER.validate_python,
            )
        )

        self.assertEqual([[row.id for row in batch] for batch in batches], [[10, 11], [12]])
        self.assertEqual(client.calls[0][1], [1, 2])
        self.assertEqual(client.calls[1][1], [4])

    def test_count_grouped_rows_by_ids_aggregates_batches(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        client = _FetchAllClientStub(
            [
                [{"group_id": 1, "total": 2}, {"group_id": 2, "total": 3}],
                [{"group_id": 3, "total": 4}],
            ]
        )

        grouped_counts = importer_model._count_grouped_rows_by_ids(
            client,
            "shipitem",
            "shipId",
            "shipId",
            [2, 1, 3, 2],
            batch_size=2,
        )

        self.assertEqual(grouped_counts, {1: 2, 2: 3, 3: 4})
        self.assertEqual(client.calls[0][1], [1, 2])
        self.assertEqual(client.calls[1][1], [3])

    def test_prefetch_external_id_records_full_includes_inactive_records(self) -> None:
        importer_model = self.env["fishbowl.importer"]
        system = self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="Fishbowl",
            applicable_model_xml_ids=(),
        )
        partner = self.env["res.partner"].create({"name": "Inactive Mapping"})
        self.env["external.id"].sudo().create(
            {
                "res_model": "sale.order.line",
                "res_id": partner.id,
                "system_id": system.id,
                "resource": "salesorderitem",
                "external_id": "123",
                "active": False,
            }
        )

        existing_map, stale_map, blocked_ids = importer_model._prefetch_external_id_records_full(
            system.id,
            "salesorderitem",
            "sale.order.line",
        )

        self.assertEqual(existing_map, {})
        self.assertIn("123", stale_map)
        self.assertEqual(blocked_ids, set())
