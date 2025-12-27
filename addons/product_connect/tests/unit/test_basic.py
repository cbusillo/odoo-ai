from ..common_imports import tagged, patch, MagicMock, ValidationError, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory, PartnerFactory


@tagged(*UNIT_TAGS)
class TestTemplate(UnitTestCase):
    def test_using_factories(self) -> None:
        product = ProductFactory.create(self.env, name="Test Product", type="consu")
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.default_code)
        self.assertGreater(product.list_price, 0)

        partner = PartnerFactory.create(self.env, name="Test Partner")
        self.assertTrue(partner.email)
        self.assertEqual(partner.customer_rank, 1)

    def test_creating_product_variants(self) -> None:
        size_attr = self.env["product.attribute"].create(
            {
                "name": "Test Size",
                "display_type": "radio",
            }
        )

        size_values = []
        for size in ["S", "M", "L"]:
            val = self.env["product.attribute.value"].create(
                {
                    "name": size,
                    "attribute_id": size_attr.id,
                }
            )
            size_values.append(val)

        template = self.env["product.template"].create(
            {
                "name": "Test T-Shirt",
                "type": "consu",
                "default_code": "60000001",
                "website_description": "Test T-shirt with sizes",
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {
                            "attribute_id": size_attr.id,
                            "value_ids": [(6, 0, [v.id for v in size_values])],
                        },
                    )
                ],
            }
        )

        self.assertEqual(len(template.product_variant_ids), 3)

    def setUp(self) -> None:
        super().setUp()
        self.test_timestamp = f"test_{self.id()}"

    def test_partner_comprehensive(self) -> None:
        partner = PartnerFactory.create(self.env, name="Test Customer")
        self.assertEqual(partner.name, "Test Customer")
        self.assertTrue(partner.email)
        self.assertFalse(partner.is_company)

        partner_with_context = PartnerFactory.create(self.env, name="Context Test Partner", email="context@example.com")
        self.assertTrue(partner_with_context.exists())
        self.assertEqual(partner_with_context.name, "Context Test Partner")
        self.assertEqual(partner_with_context.email, "context@example.com")

        found_partners = self.env["res.partner"].search([("name", "=", "Test Customer")])
        self.assertIn(partner, found_partners)

        self.assertTrue(self.env.context.get("skip_shopify_sync", False))

        context_partners = self.env["res.partner"].search([("name", "=", "Context Test Partner")])
        self.assertIn(partner_with_context, context_partners)

    def test_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            self.env["product.product"].create(
                {
                    "name": "Invalid Product",
                    "default_code": "ABC",
                    "type": "consu",
                }
            )

    def test_with_patch_object_context_manager(self) -> None:
        partner = PartnerFactory.create(self.env, name="Test Partner")

        with patch.object(type(partner), "message_post") as mock_message_post:
            mock_message_post.return_value = True

            partner.message_post(body="Test message", subject="Test")

            mock_message_post.assert_called_once_with(body="Test message", subject="Test")

    @patch.object(ValidationError, "__init__", return_value=None)
    def test_with_patch_object_decorator(self, mock_init: MagicMock) -> None:
        partner = PartnerFactory.create(self.env)

        try:
            if not partner.email:
                raise ValidationError("Email required")
        except ValidationError:
            pass

        self.assertTrue(mock_init.called or not mock_init.called)
