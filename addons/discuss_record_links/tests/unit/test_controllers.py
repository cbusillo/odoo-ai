# noinspection SpellCheckingInspection
# Justification: Odoo test code uses API names like `env.ref` and test SKUs (e.g., WIDGX)
# which trigger IDE spellcheckers; suppress for this test file only.

from unittest.mock import patch

from odoo.tests import TransactionCase

from ..common_imports import tagged, UNIT_TAGS

from ...controllers.main import DiscussRecordLinks


@tagged(*UNIT_TAGS)
class TestLabelsRoute(TransactionCase):
    def setUp(self) -> None:
        super().setUp()
        # Ensure we have a product and a corresponding DRL config entry
        # Create a product
        # noinspection SpellCheckingInspection – model/field tokens (ref/sku) can trip spellcheckers in tests
        Product = self.env["product.product"].with_context(skip_sku_check=True)
        # noinspection SpellCheckingInspection – test SKU value may be flagged as a typo by IDEs
        self.product = Product.create({"name": "Widget X", "default_code": "WIDGX"})

        # Find model and fields without using env.ref to avoid IDE spellcheck noise
        model_product = self.env["ir.model"].search([("model", "=", "product.product")], limit=1)
        f_name = self.env["ir.model.fields"].search([("model_id", "=", model_product.id), ("name", "=", "name")], limit=1)
        f_code = self.env["ir.model.fields"].search([("model_id", "=", model_product.id), ("name", "=", "default_code")], limit=1)

        # Create a unique prefix for tests to avoid collisions
        self.env["discuss.record.link.config"].create(
            {
                "active": True,
                "prefix": "tpro",
                "label": "Products",
                "model_id": model_product.id,
                "search_field_ids": [(6, 0, [f_name.id, f_code.id])],
                "display_template": "[{{ default_code }}] {{ name }}",
                "limit": 8,
            }
        )

    def test_labels_returns_rendered_template(self) -> None:
        ctl = DiscussRecordLinks()

        _req = type("_Req", (), {})()
        _req.env = self.env
        with patch("odoo.addons.discuss_record_links.controllers.main.request", _req):
            rows = ctl.labels(targets=[{"model": "product.product", "id": self.product.id}])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], "product.product")
        self.assertEqual(rows[0]["id"], self.product.id)
        self.assertEqual(rows[0]["label"], f"[{self.product.default_code}] {self.product.name}")

    def test_labels_fallback_display_name_for_unconfigured_model(self) -> None:
        partner = self.env["res.partner"].create({"name": "Acme"})
        ctl = DiscussRecordLinks()

        _req = type("_Req", (), {})()
        _req.env = self.env
        with patch("odoo.addons.discuss_record_links.controllers.main.request", _req):
            rows = ctl.labels(targets=[{"model": "res.partner", "id": partner.id}])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], partner.display_name)


@tagged(*UNIT_TAGS)
class TestSearchRoute(TransactionCase):
    def setUp(self) -> None:
        super().setUp()
        Product = self.env["product.product"].with_context(skip_sku_check=True)
        self.p1 = Product.create({"name": "Widget Alpha", "default_code": "A1"})
        self.p2 = Product.create({"name": "Widget Beta", "default_code": "B2"})

        model_product = self.env.ref("product.model_product_product")
        f_name = self.env["ir.model.fields"].search([("model_id", "=", model_product.id), ("name", "=", "name")], limit=1)
        # Create a config with prefix 'tpro2'
        self.env["discuss.record.link.config"].create(
            {
                "active": True,
                "prefix": "tpro2",
                "label": "Products",
                "model_id": model_product.id,
                "search_field_ids": [(6, 0, [f_name.id])],
                "display_template": "[{{ default_code }}] {{ name }}",
                "limit": 8,
            }
        )

    def test_search_with_prefix_and_tokens(self) -> None:
        ctl = DiscussRecordLinks()
        term = "tpro2 widget"
        _req = type("_Req", (), {})()
        _req.env = self.env
        with patch("odoo.addons.discuss_record_links.controllers.main.request", _req):
            res = ctl.search(term=term)

        labels = {s["label"] for s in res["suggestions"]}
        self.assertIn("[A1] Widget Alpha", labels)
        self.assertIn("[B2] Widget Beta", labels)
