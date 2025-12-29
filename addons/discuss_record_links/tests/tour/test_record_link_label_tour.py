from odoo.tests import tagged

from odoo.addons.product_connect.tests.base_types import TOUR_TAGS
from odoo.addons.product_connect.tests.fixtures.base import TourTestCase


@tagged(*TOUR_TAGS)
class TestRecordLinkLabelTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Seed a known product and DRL config for product.product
        Product = cls.env["product.product"].with_context(skip_sku_check=True)
        prod = Product.search([("default_code", "=", "WIDGET-E2E")], limit=1)
        if not prod:
            prod = Product.create({"name": "Widget E2E", "default_code": "WIDGET-E2E"})

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

    def test_record_link_label_tour(self) -> None:
        self.start_tour("/odoo", "drl_record_link_label", login=self._get_test_login(), timeout=180)
