from odoo.tests import tagged

from odoo.addons.product_connect.tests.base_types import TOUR_TAGS
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase


@tagged(*TOUR_TAGS)
class TestRecordLinkInsertTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Ensure a product exists that matches the tour query ("widget")
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        # If one already exists, don't duplicate
        existing = Product.search([("name", "ilike", "widget")], limit=1)
        if not existing:
            Product.create({"name": "Widget Tour", "default_code": "WIDGET-T"})

    def test_record_link_insert_tour(self) -> None:
        # Use Discuss root; the tour navigates from the Apps grid
        self.start_tour("/odoo", "drl_record_link_insert", login=self._get_test_login())
