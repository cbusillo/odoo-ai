from odoo.addons.product_connect.tests.base_types import TOUR_TAGS
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase
from odoo.tests import tagged


@tagged(*TOUR_TAGS)
class TestRecordLinkFidLabelTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Seed a product with a predictable default_code for assertion
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        prod = Product.search([("default_code", "=", "WIDGET-FID")], limit=1)
        if not prod:
            Product.create({"name": "Widget FID", "default_code": "WIDGET-FID"})

        # Ensure DRL config for product.product exists (data file defines 'pro')
        # No action needed unless disabled; keep test minimal

    def test_record_link_fid_label_tour(self) -> None:
        self.start_tour("/odoo", "drl_record_link_fid_label", login=self._get_test_login(), timeout=180)
