from odoo.tests import tagged

from odoo.addons.opw_custom.tests.base_types import TOUR_TAGS
from odoo.addons.opw_custom.tests.fixtures.base import TourTestCase


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
            Product.create({"name": "Widget Tour", "default_code": "1003"})

        channel_record = cls.env["discuss.channel"].search([("name", "=", "DRL Tour")], limit=1)
        if not channel_record:
            channel_record = cls.env["discuss.channel"].create({"name": "DRL Tour"})
        channel_record.add_members(
            partner_ids=[cls.test_user.partner_id.id],
            post_joined_message=False,
        )
        channel_record.with_user(cls.test_user).channel_pin(pinned=True)
        cls._drl_active_id = f"discuss.channel_{channel_record.id}"

    def test_record_link_insert_tour(self) -> None:
        start_url = f"/odoo/action-mail.action_discuss?active_id={self._drl_active_id}"
        self.start_tour(start_url, "drl_record_link_insert", login=self._get_test_login(), timeout=300)
