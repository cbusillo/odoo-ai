from ..common_imports import tagged, TOUR_TAGS
from ..fixtures.base import TourTestCase


@tagged(*TOUR_TAGS, "opw_custom")
class TestMultigraphTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from datetime import date

        cls.tour_products = cls.env["product.template"].create(
            [
                {
                    "name": f"Tour Product {i}",
                    "default_code": f"{30000 + i}",  # Valid SKU
                    "list_price": 200 * i,
                    "standard_price": 120 * i,
                    "type": "consu",
                    "is_ready_for_sale": True,
                    "is_ready_for_sale_last_enabled_date": date(2025, 1, i),
                    "initial_quantity": 30 * i,
                    "initial_price_total": 3000 * i,
                    "initial_cost_total": 1800 * i,
                }
                for i in range(1, 6)
            ]
        )

    def test_multigraph_view_tour(self) -> None:
        # Land directly on the analytics action to avoid flaky doAction flows
        # Graph views can be slower to load on CI; give them a bit more time
        # Force initial view to pivot to avoid multigraph controller dev-only sample model path
        self.start_tour(
            "/web#action=opw_custom.action_product_processing_analytics&view_type=pivot",
            "test_multigraph_view",
            timeout=180,
        )
