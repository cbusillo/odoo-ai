from ..common_imports import TOUR_TAGS, date, tagged
from ..fixtures.base import TourTestCase
from ..fixtures.factories import ProductFactory


@tagged(*TOUR_TAGS, "product_connect")
class TestMultigraphSimple(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.test_products = [
            ProductFactory.create(
                cls.env,
                name=f"Ready Product {i}",
                default_code=f"{20000 + i}",  # Valid SKU
                list_price=150 * i,
                standard_price=90 * i,
                is_ready_for_sale=True,
                is_ready_for_sale_last_enabled_date=date(2025, 1, i),
                initial_quantity=20 * i,
                initial_price_total=2000 * i,
                initial_cost_total=1200 * i,
            )
            for i in range(1, 6)
        ]

    def test_action_loads(self) -> None:
        """Test that action exists and has correct configuration"""
        action = self.env.ref("product_connect.action_product_processing_analytics")
        self.assertTrue(action, "Action should exist")
        self.assertEqual(action.res_model, "product.template")
        self.assertIn("graph", action.view_mode)

        # Test that the model can be accessed (basic permissions check)
        model = self.env[action.res_model]
        self.assertTrue(hasattr(model, "search"), "Should be able to access product.template model")

        # Check that we can run a basic search with the domain from the action
        domain = eval(action.domain) if action.domain else []
        try:
            # This should not raise an exception even if no records are found
            model.search(domain, limit=1)
            # The search succeeded (even if it returned no records)
            self.assertTrue(True, "Domain search completed without error")
        except Exception as e:
            self.fail(f"Domain search failed: {e}")

        # Verify that our test data matches the action domain
        test_product_ids = set(p.id for p in self.test_products)
        matching_products = model.search(domain)
        matching_test_products = matching_products.filtered(lambda p: p.id in test_product_ids)

        self.assertGreater(len(matching_test_products), 0, "Action domain should find our test products")

        import logging

        _logger = logging.getLogger(__name__)
        _logger.info(f"✓ Action loads test completed - found {len(matching_test_products)} matching products")

    def test_direct_graph_view(self) -> None:
        """Test that graph views are properly configured and accessible"""
        # Create additional test products for this specific test
        additional_products = [
            ProductFactory.create(
                self.env,
                name=f"Test Product {i}",
                default_code=f"{1000 + i}",
                list_price=100 + i * 10,
                is_ready_for_sale=True,
                is_ready_for_sale_last_enabled_date="2025-01-01",
                initial_quantity=10,
                initial_price_total=1000,
                initial_cost_total=500,
            )
            for i in range(3)
        ]

        action = self.env.ref("product_connect.action_product_processing_analytics")

        # Test that action supports multiple view modes including multigraph
        view_modes = action.view_mode.split(",")
        self.assertIn("multigraph", view_modes, "Action should support multigraph view mode")

        # Test that we can access the model and run searches
        model = self.env[action.res_model]
        domain = eval(action.domain) if action.domain else []

        # Should be able to search with the action's domain
        all_matching = model.search(domain)
        self.assertIsInstance(all_matching, type(model), "Search should return recordset")

        # Test that context has proper configuration for graph views
        context = eval(action.context) if action.context else {}
        if "graph_measures" in context:
            for measure in context["graph_measures"]:
                self.assertTrue(hasattr(model, measure), f"Model should have measure field: {measure}")

        # Test that our additional products are included in results
        additional_product_ids = set(p.id for p in additional_products)
        matching_additional = all_matching.filtered(lambda p: p.id in additional_product_ids)
        self.assertGreater(len(matching_additional), 0, "Should find our additional test products")

        # Test that required fields exist on the model for graph rendering
        required_fields = ["name", "list_price", "is_ready_for_sale"]
        for field in required_fields:
            self.assertTrue(hasattr(model, field), f"Model should have required field: {field}")

        import logging

        _logger = logging.getLogger(__name__)
        _logger.info(f"✓ Direct graph view test completed - {len(matching_additional)} additional products found")
