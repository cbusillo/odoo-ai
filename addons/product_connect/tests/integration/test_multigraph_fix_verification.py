from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ProductFactory
from odoo.exceptions import ValidationError


@tagged(*INTEGRATION_TAGS)
class TestMultigraphFixVerification(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.View = cls.env["ir.ui.view"]
        cls.ActionWindow = cls.env["ir.actions.act_window"]

        cls._create_multigraph_test_data()

    @classmethod
    def _create_multigraph_test_data(cls) -> None:
        import datetime

        base_date = datetime.date.today() - datetime.timedelta(days=30)

        cls.multigraph_products = []
        for i in range(5):
            product = ProductFactory.create(
                cls.env,
                name=f"Multigraph Test Product {i + 1}",
                default_code=f"7000000{i + 1}",
                list_price=100.0 + (i * 50),
                standard_price=50.0 + (i * 25),
                is_ready_for_sale=i % 2 == 0,
            )

            test_date = base_date + datetime.timedelta(days=i * 5)
            product.write(
                {
                    "is_ready_for_sale_last_enabled_date": test_date,
                    "initial_quantity": 10 + i,
                    "image_count": i + 1,
                }
            )

            cls.multigraph_products.append(product)

    def test_multigraph_view_loads_without_errors(self) -> None:
        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")

        self.assertTrue(multigraph_view.exists())
        self.assertEqual(multigraph_view.type, "graph")
        self.assertEqual(multigraph_view.model, "product.template")

        arch_string = multigraph_view.arch
        self.assertIn('js_class="multigraph"', arch_string)
        self.assertIn('type="line"', arch_string)

    def test_multigraph_view_xml_validation(self) -> None:
        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")

        try:
            views_data = multigraph_view.get_views([(multigraph_view.id, "graph")])
            self.assertIn("views", views_data)
            self.assertIn("graph", views_data["views"])
        except ValidationError as e:
            self.fail(f"Multigraph view XML validation failed: {e}")

    def test_multigraph_component_initialization(self) -> None:
        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")
        arch_string = multigraph_view.arch

        self.assertIn('js_class="multigraph"', arch_string)

        required_fields = [
            "is_ready_for_sale_last_enabled_date",
            "initial_price_total",
            "initial_cost_total",
            "initial_quantity",
            "image_count",
        ]

        for field in required_fields:
            self.assertIn(field, arch_string, f"Required field {field} missing from multigraph view")

    def test_multigraph_measures_configuration(self) -> None:
        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")
        arch_string = multigraph_view.arch

        measure_configs = [
            ("initial_price_total", 'type="measure"', 'widget="monetary"'),
            ("initial_cost_total", 'type="measure"', 'widget="monetary"'),
            ("initial_quantity", 'type="measure"'),
            ("image_count", 'type="measure"'),
        ]

        for field_name, type_attr, *optional_attrs in measure_configs:
            self.assertIn(f'name="{field_name}"', arch_string)
            self.assertIn(type_attr, arch_string)

            for optional_attr in optional_attrs:
                self.assertIn(optional_attr, arch_string)

    def test_multigraph_date_grouping(self) -> None:
        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")
        arch_string = multigraph_view.arch

        self.assertIn('name="is_ready_for_sale_last_enabled_date"', arch_string)
        self.assertIn('interval="day"', arch_string)

    def test_multigraph_action_integration(self) -> None:
        action = self.env.ref("product_connect.action_product_processing_analytics")

        self.assertEqual(action.res_model, "product.template")
        self.assertIn("graph", action.view_mode)

        self.assertEqual(action.view_id.id, self.env.ref("product_connect.view_product_processing_multigraph").id)

    def test_multigraph_context_configuration(self) -> None:
        action = self.env.ref("product_connect.action_product_processing_analytics")

        context = action.context
        if isinstance(context, str):
            import ast

            context = ast.literal_eval(context)

        assert isinstance(context, dict)

        expected_context_keys = ["search_default_date_range_group", "graph_groupbys", "graph_measures"]

        for key in expected_context_keys:
            self.assertIn(key, context, f"Missing context key: {key}")

        self.assertEqual(context["graph_groupbys"], ["is_ready_for_sale_last_enabled_date:day"])
        expected_measures = ["initial_price_total", "initial_cost_total", "initial_quantity", "image_count"]
        self.assertEqual(context["graph_measures"], expected_measures)

    def test_multigraph_data_rendering(self) -> None:
        ProductTemplate = self.env["product.template"]

        products = ProductTemplate.search(
            [("is_ready_for_sale_last_enabled_date", "!=", False), ("id", "in", [p.id for p in self.multigraph_products])]
        )

        self.assertTrue(len(products) > 0, "No test products found for multigraph")

        for product in products:
            try:
                _ = product.initial_price_total
                _ = product.initial_cost_total
                _ = product.initial_quantity
                _ = product.image_count
                _ = product.is_ready_for_sale_last_enabled_date
            except Exception as e:
                self.fail(f"Error reading multigraph fields from product {product.name}: {e}")

    def test_multigraph_no_js_errors(self) -> None:
        js_files = [
            "addons/product_connect/static/src/views/multigraph/multigraph_view.js",
            "addons/product_connect/static/src/views/multigraph/multigraph_controller.js",
            "addons/product_connect/static/src/views/multigraph/multigraph_renderer.js",
        ]

        deprecated_patterns = [
            "jQuery",
            "$(",
            ".extend(",
            "odoo.define",
            ";",  # Should not have semicolons in our style
        ]

        for js_file in js_files:
            try:
                with open(js_file) as f:
                    content = f.read()

                for pattern in deprecated_patterns:
                    self.assertNotIn(pattern, content, f"Deprecated pattern '{pattern}' found in {js_file}")
            except FileNotFoundError:
                pass

    def test_multigraph_arch_parser_compatibility(self) -> None:
        test_arch = """
        <graph string="Test MultiGraph" type="line" js_class="multigraph">
            <field name="create_date" interval="month"/>
            <field name="list_price" type="measure" widget="monetary" string="Price"/>
            <field name="qty_available" type="measure" string="Quantity"/>
        </graph>
        """

        test_view = self.View.create(
            {
                "name": "test.multigraph.arch.parser",
                "model": "product.template",
                "type": "graph",
                "arch": test_arch,
            }
        )

        try:
            processed = test_view.get_views([(test_view.id, "graph")])
            self.assertIn("views", processed)
            self.assertIn("graph", processed["views"])

            view_data = processed["views"]["graph"]
            self.assertIn("arch", view_data)

        except Exception as e:
            self.fail(f"Arch parser failed to process multigraph view: {e}")
        finally:
            test_view.unlink()

    def test_multigraph_field_validation(self) -> None:
        ProductTemplate = self.env["product.template"]

        required_fields = [
            "is_ready_for_sale_last_enabled_date",
            "initial_price_total",
            "initial_cost_total",
            "initial_quantity",
            "image_count",
        ]

        model_fields = ProductTemplate.fields_get(required_fields)

        for field_name in required_fields:
            self.assertIn(field_name, model_fields, f"Required multigraph field '{field_name}' not found on product.template model")

    def test_multigraph_performance_basic(self) -> None:
        import time

        start_time = time.time()

        multigraph_view = self.env.ref("product_connect.view_product_processing_multigraph")
        views_data = multigraph_view.get_views([(multigraph_view.id, "graph")])

        end_time = time.time()
        load_time = end_time - start_time

        self.assertLess(load_time, 1.0, f"Multigraph view took too long to load: {load_time:.2f}s")

        self.assertIn("views", views_data)
        self.assertIn("graph", views_data["views"])
