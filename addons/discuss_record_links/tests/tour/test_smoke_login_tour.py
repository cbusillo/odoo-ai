from __future__ import annotations

from odoo.addons.product_connect.tests.base_types import TOUR_TAGS
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase
from odoo.tests import tagged


@tagged(*TOUR_TAGS, "discuss_record_links")
class TestDiscussRecordLinksSmokeTour(TourTestCase):
    def test_smoke_login_tour(self) -> None:
        self.start_tour("/web", "smoke_login_tour", login=self._get_test_login(), timeout=120)
