from ...models.fishbowl_import_constants import (
    LEGACY_BUCKET_ADHOC,
    LEGACY_BUCKET_DISCOUNT,
    LEGACY_BUCKET_FEE,
    LEGACY_BUCKET_MISC,
    LEGACY_BUCKET_SHIPPING,
)
from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestFishbowlHelpers(UnitTestCase):
    def test_to_bool(self) -> None:
        self.assertTrue(self.Importer._to_bool("true"))
        self.assertTrue(self.Importer._to_bool("1"))
        self.assertFalse(self.Importer._to_bool("0"))
        self.assertFalse(self.Importer._to_bool(None))
        self.assertTrue(self.Importer._to_bool(b"\x01"))
        self.assertFalse(self.Importer._to_bool(b"\x00"))

    def test_legacy_bucket_for_line(self) -> None:
        self.assertEqual(self.Importer._legacy_bucket_for_line("UPS shipping", 10.0), LEGACY_BUCKET_SHIPPING)
        self.assertEqual(self.Importer._legacy_bucket_for_line("handling fee", 5.0), LEGACY_BUCKET_FEE)
        self.assertEqual(self.Importer._legacy_bucket_for_line("promo discount", 5.0), LEGACY_BUCKET_DISCOUNT)
        self.assertEqual(self.Importer._legacy_bucket_for_line("misc charge", 5.0), LEGACY_BUCKET_MISC)
        self.assertEqual(self.Importer._legacy_bucket_for_line("random item", 5.0), LEGACY_BUCKET_ADHOC)
        self.assertEqual(self.Importer._legacy_bucket_for_line("discount", -1.0), LEGACY_BUCKET_DISCOUNT)

    def test_build_legacy_line_name(self) -> None:
        line_name = self.Importer._build_legacy_line_name("Widget", "SKU-1", None)
        self.assertEqual(line_name, "SKU-1 - Widget")
        line_name = self.Importer._build_legacy_line_name("SKU-1 - Widget", "SKU-1", None)
        self.assertEqual(line_name, "SKU-1 - Widget")

    def test_product_type_field(self) -> None:
        template_model = self.env["product.template"]
        field_name = self.Importer._product_type_field(template_model)
        self.assertIn(field_name, {"detailed_type", "type"})
