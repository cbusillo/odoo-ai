from types import SimpleNamespace
from unittest.mock import patch

from ...models import repairshopr_sales
from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestRepairshoprPricingCatalog(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.RepairshoprImporter

    def test_extract_price_prefers_exact_header_match(self) -> None:
        row_map = {
            "Price 10%": "110",
            "Price": "100",
        }

        parsed = repairshopr_sales.RepairshoprPricingCatalog._extract_price(row_map, ["price"])

        self.assertEqual(parsed, 100.0)

    def test_extract_price_handles_deduped_duplicate_exact_headers(self) -> None:
        row_map = {
            "Price": "120",
            "Price__2": "100",
        }

        parsed = repairshopr_sales.RepairshoprPricingCatalog._extract_price(row_map, ["price"])

        self.assertEqual(parsed, 100.0)

    def test_extract_price_ignores_percentage_columns_when_no_base_price(self) -> None:
        row_map = {
            "Pricing 10%": "110",
            "Pricing 15%": "115",
        }

        parsed = repairshopr_sales.RepairshoprPricingCatalog._extract_price(row_map, ["pricing", "price"])

        self.assertIsNone(parsed)

    def test_extract_price_is_deterministic_when_multiple_columns_match(self) -> None:
        row_map = {
            "List Price": "120",
            "Base Price": "100",
        }

        parsed = repairshopr_sales.RepairshoprPricingCatalog._extract_price(row_map, ["price"])

        self.assertEqual(parsed, 100.0)

    def test_extract_price_respects_preferred_column_order(self) -> None:
        row_map = {
            "Price": "100",
            "Pricing": "90",
        }

        parsed = repairshopr_sales.RepairshoprPricingCatalog._extract_price(row_map, ["pricing", "price"])

        self.assertEqual(parsed, 90.0)

    def test_get_pricing_catalog_caches_on_model_class(self) -> None:
        type(self.importer)._pricing_catalog = None
        sentinel_catalog = repairshopr_sales.RepairshoprPricingCatalog({"regular": {}})
        with patch.object(
            repairshopr_sales.RepairshoprPricingCatalog,
            "load",
            return_value=sentinel_catalog,
        ) as load_mock:
            self.assertIs(self.importer._get_pricing_catalog(), sentinel_catalog)
            self.assertIs(self.importer._get_pricing_catalog(), sentinel_catalog)

        load_mock.assert_called_once_with()
        type(self.importer)._pricing_catalog = None

    def test_apply_rework_labor_adjustment_decrements_only_one_labor_line(self) -> None:
        line_commands = [
            (0, 0, {"name": "Labor", "product_uom_qty": 2}),
            (0, 0, {"name": "Labor", "product_uom_qty": 2}),
        ]
        billing_contract = SimpleNamespace(policy_id=SimpleNamespace(labor_product_id=None))

        adjusted = self.importer._apply_rework_labor_adjustment(line_commands, True, billing_contract)

        self.assertEqual(adjusted[0][2]["product_uom_qty"], 1)
        self.assertEqual(adjusted[1][2]["product_uom_qty"], 2)

    def test_apply_rework_labor_adjustment_removes_only_one_single_quantity_line(self) -> None:
        line_commands = [
            (0, 0, {"name": "Labor", "quantity": 1}),
            (0, 0, {"name": "Labor", "quantity": 1}),
        ]
        billing_contract = SimpleNamespace(policy_id=SimpleNamespace(labor_product_id=None))

        adjusted = self.importer._apply_rework_labor_adjustment(line_commands, True, billing_contract)

        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0][2]["quantity"], 1)
