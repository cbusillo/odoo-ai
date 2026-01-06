from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory


@tagged(*UNIT_TAGS)
class TestMultigraphPython(UnitTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.products_with_metrics = []

        for i in range(3):
            product = ProductFactory.create(
                cls.env,
                name=f"January Product {i + 1}",
                default_code=f"6000000{i + 1}",
                list_price=100.0 + (i * 10),
                standard_price=60.0 + (i * 5),
                initial_quantity=100 + (i * 10),
                is_ready_for_sale=True,
                is_ready_for_sale_last_enabled_date=f"2024-01-{15 + i}",
            )
            cls.products_with_metrics.append(product)

        for i in range(3):
            product = ProductFactory.create(
                cls.env,
                name=f"February Product {i + 1}",
                default_code=f"6000001{i + 1}",
                list_price=100.0 + (i * 10),
                standard_price=60.0 + (i * 5),
                initial_quantity=150 + (i * 15),
                is_ready_for_sale=True,
                is_ready_for_sale_last_enabled_date=f"2024-02-{10 + i}",
            )
            cls.products_with_metrics.append(product)

    def test_multigraph_view_exists(self) -> None:
        view = self.env["ir.ui.view"].search(
            [
                ("name", "=", "product.processing.multigraph"),
                ("model", "=", "product.template"),
            ]
        )
        self.assertTrue(view, "Multigraph view should exist")
        self.assertIn("Product Processing Analytics", view.arch_db)

    def test_multigraph_data_aggregation(self) -> None:
        result = (
            self.env["product.template"]
            .with_context(skip_shopify_sync=False)
            .read_group(
                domain=[
                    ("is_ready_for_sale", "=", True),
                    ("id", "in", [p.id for p in self.products_with_metrics]),
                ],
                fields=["initial_price_total:sum", "initial_cost_total:sum", "initial_quantity:sum"],
                groupby=["is_ready_for_sale_last_enabled_date:month"],
            )
        )

        self.assertEqual(len(result), 2, "Should have 2 months of data")

        jan_data = next((r for r in result if "January" in r.get("is_ready_for_sale_last_enabled_date:month", "")), None)
        self.assertIsNotNone(jan_data)
        self.assertGreater(jan_data["initial_price_total"], 0, "January price total should be > 0")
        self.assertGreater(jan_data["initial_cost_total"], 0, "January cost total should be > 0")
        self.assertGreater(jan_data["initial_quantity"], 0, "January quantity should be > 0")

    def test_multigraph_with_domain_filter(self) -> None:
        result = (
            self.env["product.template"]
            .with_context(skip_shopify_sync=False)
            .read_group(
                domain=[
                    ("is_ready_for_sale", "=", True),
                    ("initial_price_total", ">", 12000),
                    ("id", "in", [p.id for p in self.products_with_metrics]),
                ],
                fields=["initial_price_total:sum", "initial_quantity:sum"],
                groupby=["is_ready_for_sale_last_enabled_date:month"],
            )
        )

        self.assertGreater(len(result), 0, "Should have at least one result")
        total_price = sum(r["initial_price_total"] for r in result)
        self.assertGreater(total_price, 0)
        all_products_result = (
            self.env["product.template"]
            .with_context(skip_shopify_sync=False)
            .read_group(
                domain=[
                    ("is_ready_for_sale", "=", True),
                    ("id", "in", [p.id for p in self.products_with_metrics]),
                ],
                fields=["initial_price_total:sum"],
                groupby=["is_ready_for_sale_last_enabled_date:month"],
            )
        )
        all_total = sum(r["initial_price_total"] for r in all_products_result)
        self.assertLess(total_price, all_total, "Filtered total should be less than all products total")

    def test_multigraph_multiple_groupby(self) -> None:
        root_category = self.env["product.category"].search([("parent_id", "=", False)], limit=1)
        if not root_category:
            root_category = self.env["product.category"].create({"name": "All"})
        secondary_category = self.env["product.category"].create({"name": "Test Category", "parent_id": root_category.id})

        for i, product in enumerate(self.products_with_metrics):
            product.write(
                {
                    "categ_id": root_category.id if i % 2 == 0 else secondary_category.id,
                }
            )

        result = self.env["product.template"].read_group(
            domain=[("is_ready_for_sale", "=", True)],
            fields=["initial_price_total:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:month", "categ_id"],
        )

        self.assertGreater(len(result), 2, "Should have more groups with category grouping")

    def test_multigraph_empty_data(self) -> None:
        result = self.env["product.template"].read_group(
            domain=[("id", "=", 0)],
            fields=["initial_price_total:sum", "initial_cost_total:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:month"],
        )

        self.assertEqual(len(result), 0, "Should return empty result for no data")

    def test_multigraph_null_values(self) -> None:
        product_null = ProductFactory.create(
            self.env,
            name="Product with Null Metrics",
            default_code="70000001",
            initial_price_total=0.0,
            initial_cost_total=0.0,
            initial_quantity=0,
            is_ready_for_sale=True,
            is_ready_for_sale_last_enabled_date="2024-03-01",
        )

        result = self.env["product.template"].read_group(
            domain=[("id", "=", product_null.id)],
            fields=["initial_price_total:sum", "initial_cost_total:sum", "initial_quantity:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:month"],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["initial_price_total"], 0.0)
        self.assertEqual(result[0]["initial_quantity"], 0)

    def test_multigraph_monetary_formatting(self) -> None:
        field_price = self.env["product.template"]._fields["initial_price_total"]
        field_cost = self.env["product.template"]._fields["initial_cost_total"]

        self.assertEqual(field_price.type, "float")
        self.assertEqual(field_cost.type, "float")

    def test_multigraph_date_intervals(self) -> None:
        result_day = self.env["product.template"].read_group(
            domain=[("is_ready_for_sale", "=", True)],
            fields=["initial_price_total:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:day"],
        )

        result_month = self.env["product.template"].read_group(
            domain=[("is_ready_for_sale", "=", True)],
            fields=["initial_price_total:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:month"],
        )

        self.assertGreaterEqual(len(result_day), len(result_month))

    def test_multigraph_access_rights(self) -> None:
        test_user = self.env["res.users"].create(
            {
                "name": "Multigraph Test User",
                "login": "multigraph_test",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

        ProductTemplate = self.env["product.template"].with_user(test_user)

        result = ProductTemplate.read_group(
            domain=[],
            fields=["initial_price_total:sum"],
            groupby=["is_ready_for_sale_last_enabled_date:month"],
        )

        self.assertIsInstance(result, list)

    def test_multigraph_computed_measures(self) -> None:
        products = self.env["product.template"].search([("id", "in", [p.id for p in self.products_with_metrics])])

        self.assertTrue(products, "Should have test products")
        self.assertEqual(len(products), len(self.products_with_metrics))

        self.assertIn("initial_price_total", products._fields)
        self.assertIn("initial_cost_total", products._fields)

        for product in products:
            expected_margin = product.initial_price_total - product.initial_cost_total
            if "initial_margin" in product._fields:
                actual_margin = getattr(product, "initial_margin", 0)
                self.assertAlmostEqual(
                    actual_margin, expected_margin, places=2, msg=f"Margin calculation incorrect for {product.name}"
                )
            else:
                self.assertGreater(expected_margin, 0, "Margin should be positive")
