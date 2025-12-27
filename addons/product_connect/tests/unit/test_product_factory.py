from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestProductFactory(UnitTestCase):
    def test_create_single_product(self) -> None:
        product = ProductFactory.create(self.env, name="Test Motor")

        self.assertTrue(product)
        self.assertEqual(product.name, "Test Motor")
        self.assertEqual(product.type, "consu")
        self.assertEqual(product.list_price, 100.0)
        self.assertTrue(product.default_code)
        self.assertTrue(len(product.default_code) == 8)

    def test_create_batch_products(self) -> None:
        products = ProductFactory.create_batch(self.env, count=3)

        self.assertEqual(len(products), 3)

        skus = [p.default_code for p in products]
        self.assertEqual(len(skus), len(set(skus)))

    def test_create_product_with_variants(self) -> None:
        product = ProductFactory.create_with_variants(self.env, variant_count=4, name="Multi-variant Product")

        self.assertEqual(product.name, "Multi-variant Product")
        self.assertEqual(len(product.product_variant_ids), 4)

        colors = product.product_variant_ids.mapped("product_template_attribute_value_ids.name")
        self.assertEqual(len(colors), 4)
        self.assertIn("Red", colors)
        self.assertIn("Blue", colors)

    def test_mock_service(self) -> None:
        mock_some_service = self.mock_service("odoo.addons.product_connect.models.product_template.ProductTemplate")
        mock_some_service.return_value = "mocked"

        self.assertIsNotNone(mock_some_service)
        self.assertEqual(mock_some_service.return_value, "mocked")

    def test_assert_record_values(self) -> None:
        product = ProductFactory.create(self.env, name="Test Product", list_price=250.0, standard_price=150.0)

        expected_values = {
            "name": "Test Product",
            "list_price": 250.0,
            "standard_price": 150.0,
            "type": "consu",
        }
        self.assertRecordValues(product, expected_values)
