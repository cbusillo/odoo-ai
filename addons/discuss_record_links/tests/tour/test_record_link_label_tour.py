from odoo.addons.opw_custom.tests.base_types import TOUR_TAGS
from odoo.addons.opw_custom.tests.fixtures.base import TourTestCase
from odoo.tests import tagged


@tagged(*TOUR_TAGS)
class TestRecordLinkLabelTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Seed a known product and DRL config for product.product
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        prod = Product.search([("default_code", "=", "1004")], limit=1)
        if not prod:
            Product.create({"name": "Widget E2E", "default_code": "1004"})

        model_product = cls.env["ir.model"].search([("model", "=", "product.product")], limit=1)
        f_name = cls.env["ir.model.fields"].search([("model_id", "=", model_product.id), ("name", "=", "name")], limit=1)
        # Ensure DRL config exists with prefix used by the tour (tproe2e)
        Config = cls.env["discuss.record.link.config"]
        existing = Config.search([("prefix", "=", "tproe2e")], limit=1)
        if not existing:
            Config.create(
                {
                    "active": True,
                    "prefix": "tproe2e",
                    "label": "Products",
                    "model_id": model_product.id,
                    "search_field_ids": [(6, 0, [f_name.id])],
                    "display_template": "[{{ default_code }}] {{ name }}",
                    "limit": 8,
                }
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

    def test_record_link_label_tour(self) -> None:
        start_url = f"/odoo/action-mail.action_discuss?active_id={self._drl_active_id}"
        self.start_tour(start_url, "drl_record_link_label", login=self._get_test_login(), timeout=300)
