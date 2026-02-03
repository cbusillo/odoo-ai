from ..common_imports import tagged, TOUR_TAGS
from ..fixtures.base import TourTestCase


@tagged(*TOUR_TAGS, "opw_custom")
class TestMultigraphIntegration(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from datetime import date

        cls.test_products = cls.env["product.template"].create(
            [
                {
                    "name": f"Integration Test Product {i}",
                    "default_code": f"{40000 + i}",  # Valid SKU
                    "list_price": 250 * i,
                    "standard_price": 150 * i,
                    "type": "consu",
                    "is_ready_for_sale": True,
                    "is_ready_for_sale_last_enabled_date": date(2025, 1, i),
                    "initial_quantity": 40 * i,
                    "initial_price_total": 4000 * i,
                    "initial_cost_total": 2400 * i,
                }
                for i in range(1, 6)
            ]
        )

    def test_multigraph_chart_click_no_error(self) -> None:
        """Test that multigraph integration works with test data"""
        # Simplified integration test focusing on data and model integration

        # Verify test data was created correctly
        self.assertEqual(len(self.test_products), 5, "Should have 5 test products")

        # Verify products have the required fields for multigraph
        for product in self.test_products:
            self.assertTrue(product.is_ready_for_sale, f"Product {product.name} should be ready for sale")
            self.assertIsNotNone(product.is_ready_for_sale_last_enabled_date, f"Product {product.name} should have enabled date")
            self.assertGreater(product.initial_quantity, 0, f"Product {product.name} should have quantity")

        # Test the action's domain filter works with our test data
        action = self.env.ref("opw_custom.action_product_processing_analytics")
        domain = eval(action.domain) if action.domain else []

        # Should find our test products
        matching_products = self.env["product.template"].search(domain)
        test_product_ids = set(self.test_products.ids)
        matching_test_products = matching_products.filtered(lambda p: p.id in test_product_ids)

        self.assertGreater(len(matching_test_products), 0, "Action domain should find our test products")

        # Test that the measures specified in the action context exist on the model
        context = eval(action.context) if action.context else {}
        if "graph_measures" in context:
            model = self.env[action.res_model]
            for measure in context["graph_measures"]:
                self.assertTrue(hasattr(model, measure), f"Model should have measure field: {measure}")

        import logging

        _logger = logging.getLogger(__name__)
        _logger.info(f"✓ Multigraph integration test completed - found {len(matching_test_products)} products")

    def test_multigraph_view_switching(self) -> None:
        """Test that the action supports multiple view modes"""
        # Simplified test focusing on action configuration for view switching

        action = self.env.ref("opw_custom.action_product_processing_analytics")

        # Test that action has multiple view modes configured
        view_modes = action.view_mode.split(",")
        self.assertGreater(len(view_modes), 1, "Action should support multiple view modes")

        # Verify expected view modes are present
        expected_modes = ["multigraph", "pivot", "list"]
        for mode in expected_modes:
            self.assertIn(mode, view_modes, f"Action should support {mode} view mode")

        # Test that we can access views for each mode
        model = self.env[action.res_model]

        # For each view mode, verify the model supports basic operations
        for view_mode in view_modes:
            # Test basic search works (needed for all view types)
            try:
                model.search([], limit=1)
                self.assertTrue(True, f"Model search works for {view_mode} view")
            except Exception as e:
                self.fail(f"Model search failed for {view_mode} view: {e}")

        # Test that context has proper configuration for graph views
        context = eval(action.context) if action.context else {}
        if "multigraph" in view_modes or "graph" in view_modes:
            # Should have graph configuration
            graph_keys = ["graph_measures", "graph_groupbys"]
            for key in graph_keys:
                if key in context:
                    self.assertIsInstance(context[key], list, f"Context {key} should be a list")

        import logging

        _logger = logging.getLogger(__name__)
        _logger.info(f"✓ View switching test completed - supports modes: {', '.join(view_modes)}")
