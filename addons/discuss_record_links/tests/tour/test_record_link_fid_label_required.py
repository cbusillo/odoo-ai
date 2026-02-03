from odoo.tests import tagged

from odoo.addons.opw_custom.tests.base_types import TOUR_TAGS
from odoo.addons.opw_custom.tests.fixtures.base import TourTestCase


@tagged(*TOUR_TAGS)
class TestRecordLinkFidLabelRequired(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        prod = Product.search([("default_code", "=", "1002")], limit=1)
        if not prod:
            prod = Product.create({"name": "Widget FID", "default_code": "1002"})
        cls._drl_product_id = prod.id
        cls.env["ir.config_parameter"].sudo().set_param(
            "drl_product_id_fid_required",
            str(cls._drl_product_id),
        )

        channel_record = cls.env["discuss.channel"].search([("name", "=", "DRL Tour")], limit=1)
        if not channel_record:
            channel_record = cls.env["discuss.channel"].create({"name": "DRL Tour"})
        channel_record.add_members(
            partner_ids=[cls.test_user.partner_id.id],
            post_joined_message=False,
        )
        channel_record.with_user(cls.test_user).channel_pin(pinned=True)
        cls._drl_active_id = f"discuss.channel_{channel_record.id}"

    def test_record_link_fid_label_required(self) -> None:
        start_url = (
            f"/odoo/action-mail.action_discuss?active_id={self._drl_active_id}"
            f"&drl_disable=1&drl_product_id={self._drl_product_id}"
        )
        self.start_tour(
            start_url,
            "drl_record_link_fid_label_required",
            login=self._get_test_login(),
            timeout=300,
        )
