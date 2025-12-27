from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestMultigraphQuickIntegration(UnitTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from datetime import date

        cls.test_products = cls.env["product.template"].create(
            [
                {
                    "name": f"Test Product {i}",
                    "default_code": f"{10000000 + i}",
                    "list_price": 100 * i,
                    "standard_price": 60 * i,
                    "type": "consu",
                    "is_ready_for_sale": True,
                    "is_ready_for_sale_last_enabled_date": date(2025, 1, i),
                    "initial_quantity": 10 * i,
                    "initial_price_total": 1000 * i,
                    "initial_cost_total": 600 * i,
                }
                for i in range(1, 5)
            ]
        )

    def test_multigraph_action_loads_without_error(self) -> None:
        action = self.env.ref("product_connect.action_product_processing_analytics")

        self.assertTrue(action)
        self.assertEqual(action.res_model, "product.template")
        self.assertIn("multigraph", action.view_mode)

        view = self.env.ref("product_connect.view_product_processing_multigraph")
        self.assertEqual(view.type, "graph")
        self.assertIn('js_class="multigraph"', view.arch)

    def test_multigraph_data_query_works(self) -> None:
        domain = [("is_ready_for_sale", "=", True)]

        data = self.env["product.template"].read_group(
            domain=domain,
            fields=["initial_price_total", "initial_cost_total", "initial_quantity"],
            groupby=["is_ready_for_sale_last_enabled_date:day"],
        )

        self.assertGreater(len(data), 0)

        first_group = data[0]
        self.assertIn("initial_price_total", first_group)
        self.assertIn("initial_cost_total", first_group)
        self.assertIn("initial_quantity", first_group)

    def test_multigraph_view_renders_without_server_error(self) -> None:
        view = self.env.ref("product_connect.view_product_processing_multigraph")

        view_info = self.env["product.template"].get_views([(view.id, "graph")], options={"load_filters": True})

        self.assertIn("views", view_info)
        self.assertIn("graph", view_info["views"])

        graph_view = view_info["views"]["graph"]
        self.assertIn("arch", graph_view)
        self.assertIn("multigraph", graph_view["arch"])

    def test_multigraph_search_filters_work(self) -> None:
        self.env.ref("product_connect.view_product_processing_search")

        domain = [("is_ready_for_sale", "=", True)]
        products = self.env["product.template"].search(domain)

        self.assertGreater(len(products), 0)
        self.assertTrue(all(p.is_ready_for_sale for p in products))

        from datetime import date

        date_domain = [
            ("is_ready_for_sale_last_enabled_date", ">=", date(2025, 1, 1)),
            ("is_ready_for_sale_last_enabled_date", "<=", date(2025, 1, 31)),
        ]
        date_products = self.env["product.template"].search(date_domain)
        self.assertGreater(len(date_products), 0)
