from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestMultigraphView(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.View = self.env["ir.ui.view"]

    def test_multigraph_view_type_registered(self) -> None:
        view = self.env.ref("opw_custom.view_product_processing_multigraph")
        self.assertEqual(view.type, "graph")
        self.assertIn('js_class="multigraph"', view.arch)

    def test_postprocess_multigraph_view(self) -> None:
        pass

    def test_create_multigraph_view(self) -> None:
        view = self.View.create(
            {
                "name": "test.multigraph.view",
                "model": "product.template",
                "type": "graph",
                "arch": """
                <graph string="Test MultiGraph" js_class="multigraph">
                    <field name="create_date" interval="month"/>
                    <field name="list_price" type="measure" widget="monetary"/>
                    <field name="qty_available" type="measure"/>
                </graph>
            """,
            }
        )

        self.assertTrue(view)
        self.assertEqual(view.type, "graph")

        processed_arch = view.get_views([(view.id, "graph")])
        self.assertIn("views", processed_arch)
        self.assertIn("graph", processed_arch["views"])

    def test_multigraph_action_window(self) -> None:
        action = self.env["ir.actions.act_window"].create(
            {
                "name": "Test MultiGraph Action",
                "res_model": "product.template",
                "view_mode": "graph,list,form",
            }
        )

        self.assertIn("graph", action.view_mode)

        view = self.View.create(
            {
                "name": "test.action.multigraph",
                "model": "product.template",
                "type": "graph",
                "arch": """
                <graph>
                    <field name="list_price" type="measure"/>
                </graph>
            """,
            }
        )

        action.view_id = view
        self.assertEqual(action.view_id.type, "graph")

    def test_product_processing_analytics_action(self) -> None:
        action = self.env.ref("opw_custom.action_product_processing_analytics")

        self.assertEqual(action.res_model, "product.template")
        self.assertIn("multigraph", action.view_mode, f"Expected 'multigraph' in view_mode, got: {action.view_mode}")
        self.assertTrue(
            action.view_mode.startswith("multigraph"), f"Expected view_mode to start with 'multigraph', got: {action.view_mode}"
        )

        context = action.context
        if isinstance(context, str):
            import ast

            context = ast.literal_eval(context)

        self.assertIsInstance(context, dict, f"Context should be dict, got: {type(context)}")
        assert isinstance(context, dict)
        self.assertIn("search_default_date_range_group", context, f"Missing search_default_date_range_group in context: {context}")
        self.assertIn("graph_groupbys", context, f"Missing graph_groupbys in context: {context}")
        self.assertEqual(
            context["graph_groupbys"],
            ["is_ready_for_sale_last_enabled_date:day"],
            f"Wrong graph_groupbys: {context.get('graph_groupbys')}",
        )

        self.assertNotIn("search_default_ready_for_sale", context)

    def test_enhanced_search_filters(self) -> None:
        search_view = self.env.ref("opw_custom.view_product_processing_search")

        arch_string = search_view.arch
        self.assertIn("last_365_days", arch_string)
        self.assertIn("date_range_group", arch_string)
        self.assertIn("Last 7 Days", arch_string)
        self.assertIn("Last 30 Days", arch_string)
        self.assertIn("groupby_processed_date", arch_string)
        self.assertIn("is_ready_for_sale_last_enabled_date", arch_string)

    def test_multigraph_view_definition(self) -> None:
        view = self.env.ref("opw_custom.view_product_processing_multigraph")

        self.assertEqual(view.model, "product.template")
        self.assertEqual(view.type, "graph")

        arch_string = view.arch
        self.assertIn("initial_price_total", arch_string)
        self.assertIn("initial_cost_total", arch_string)
        self.assertIn("initial_quantity", arch_string)
        self.assertIn("is_ready_for_sale_last_enabled_date", arch_string)

        self.assertIn('type="line"', arch_string)
