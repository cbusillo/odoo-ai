from odoo.tests import tagged

from odoo.addons.product_connect.tests.base_types import TOUR_TAGS
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase


@tagged(*TOUR_TAGS)
class TestRecordLinkFidLabelRequired(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        prod = Product.search([("default_code", "=", "WIDGET-FID")], limit=1)
        if not prod:
            Product.create({"name": "Widget FID", "default_code": "WIDGET-FID"})

    def test_record_link_fid_label_required(self) -> None:
        # This tour is expected to fail until labeler is enabled (red by design)
        # We run it to demonstrate the failing behavior; the CI harness will mark it as failure.
        self.start_tour("/odoo?drl_disable=1", "drl_record_link_fid_label_required", login=self._get_test_login(), timeout=180)
