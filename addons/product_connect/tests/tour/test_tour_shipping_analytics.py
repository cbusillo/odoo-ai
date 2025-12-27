from ..common_imports import tagged, TOUR_TAGS
from ..fixtures.base import TourTestCase


@tagged(*TOUR_TAGS, "product_connect")
class TestShippingAnalyticsTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._setup_shipping_test_data()
        cls._grant_sales_permissions()

    @classmethod
    def _grant_sales_permissions(cls) -> None:
        """Grant sales access permissions to the tour test user."""
        # Get the test user (created by parent class)
        test_user = cls.env["res.users"].search([("login", "=", "tour_test_user")], limit=1)
        if test_user:
            # Add sales manager group for full access to sales orders
            sales_manager_group = cls.env.ref("sales_team.group_sale_manager")
            user_group = cls.env.ref("base.group_user")
            test_user.sudo().write(
                {
                    "groups_id": [(4, sales_manager_group.id), (4, user_group.id)],
                }
            )

    @classmethod
    def _setup_shipping_test_data(cls) -> None:
        """Create sample sale orders with shipping data for the analytics tour."""
        # Create a test partner
        partner = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "email": "test@example.com",
            }
        )

        # Create sample sale orders with shipping data
        cls.env["sale.order"].create(
            [
                {
                    "name": "SO001",
                    "partner_id": partner.id,
                    "source_platform": "shopify",
                    "shipping_charge": 25.0,
                    "shipping_paid": 18.5,
                    "shipping_margin": 6.5,
                    "state": "sale",
                },
                {
                    "name": "SO002",
                    "partner_id": partner.id,
                    "source_platform": "ebay",
                    "shipping_charge": 15.0,
                    "shipping_paid": 20.0,
                    "shipping_margin": -5.0,
                    "state": "sale",
                },
            ]
        )

    def test_shipping_analytics_tour(self) -> None:
        self.start_tour("/odoo", "shipping_analytics_tour")
