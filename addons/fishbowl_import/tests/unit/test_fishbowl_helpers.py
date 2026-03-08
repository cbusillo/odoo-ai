from ...models import fishbowl_rows
from ...models.fishbowl_import_constants import (
    LEGACY_BUCKET_ADHOC,
    LEGACY_BUCKET_DISCOUNT,
    LEGACY_BUCKET_FEE,
    LEGACY_BUCKET_MISC,
    LEGACY_BUCKET_SHIPPING,
)
from ..common_imports import common
from ..fixtures.base import UnitTestCase


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
