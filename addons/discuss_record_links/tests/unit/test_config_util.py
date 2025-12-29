from odoo.tests import TransactionCase, tagged

from ...models.config_util import extract_template_fields, render_template, parse_prefix, ModelCfg


@tagged("post_install", "-at_install")
class TestConfigUtil(TransactionCase):
    def test_extract_template_fields(self) -> None:
        template = "[{{ default_code }}] {{ name }} ({{year}})"
        self.assertEqual(
            extract_template_fields(template),
            ["default_code", "name", "year"],
        )

    def test_render_template(self) -> None:
        template = "[{{ default_code }}] {{ name }}"
        values = {"default_code": "SKU1", "name": "Widget"}
        self.assertEqual(render_template(template, values), "[SKU1] Widget")

    def test_parse_prefix(self) -> None:
        cfg = {
            "pro": ModelCfg(
                key="pro",
                model="product.product",
                label="Products",
                search=["name"],
                display_template="[{{ default_code }}] {{ name }}",
                image_field=None,
                limit=8,
            )
        }
        # short form
        model, q = parse_prefix("pro: abc 123", cfg)
        self.assertEqual(model, "product.product")
        self.assertEqual(q, "abc 123")
        # space form
        model, q = parse_prefix("pro abc 123", cfg)
        self.assertEqual(model, "product.product")
        self.assertEqual(q, "abc 123")
        # no prefix → unchanged
        model, q = parse_prefix("hello world", cfg)
        self.assertIsNone(model)
        self.assertEqual(q, "hello world")
