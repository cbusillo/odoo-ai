import psycopg2
import secrets

from ..common_imports import tagged, ValidationError, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory, MotorFactory
from ..test_helpers import generate_unique_sku


@tagged(*UNIT_TAGS)
class TestProductTemplate(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()

    def _assert_sku_validation_error(self, invalid_skus: list[str]) -> None:
        for sku in invalid_skus:
            with self.subTest(sku=sku):
                with self.assertRaises(ValidationError) as context:
                    self.env["product.template"].create({"name": f"Test Product {sku}", "default_code": sku, "type": "consu"})
                self.assertIn("SKU must be 4-8 digits", str(context.exception))

    def test_product_creation_basic(self) -> None:
        product = ProductFactory.create(self.env, name="Test Product", type="consu")

        self.assertTrue(product.exists())
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.default_code)
        self.assertGreater(product.list_price, 0)

    def test_sku_validation_valid_numeric_skus(self) -> None:
        valid_sku_patterns = [4, 5, 6, 7, 8]
        for idx, length in enumerate(valid_sku_patterns):
            # Use deterministic SKU based on test method and index to avoid duplicates
            # Start with 9 to ensure we get the right length, add index for uniqueness
            base_num = int(f"9{idx:0{length - 1}d}")
            unique_sku = f"{base_num:0{length}d}"

            with self.subTest(sku=unique_sku):
                product = self.env["product.template"].create(
                    {"name": f"Test Product {unique_sku}", "default_code": unique_sku, "type": "consu"}
                )
                self.assertEqual(product.default_code, unique_sku)
                product.unlink()

    def test_sku_validation_invalid_alphanumeric_skus(self) -> None:
        invalid_skus = ["PROD-A", "TEST-SKU-001", "ABC123", "SKU123", "123ABC"]
        self._assert_sku_validation_error(invalid_skus)

    def test_sku_validation_invalid_length_skus(self) -> None:
        invalid_skus = ["123", "123456789", "12", "1"]
        self._assert_sku_validation_error(invalid_skus)

    def test_sku_validation_skip_for_non_consumable_products(self) -> None:
        invalid_sku = "INVALID-SKU"
        product = self.env["product.template"].create({"name": "Test Service", "default_code": invalid_sku, "type": "service"})
        self.assertEqual(product.default_code, invalid_sku)

    def test_sku_validation_bypass_with_context(self) -> None:
        invalid_sku = "INVALID-SKU"
        product = (
            self.env["product.template"]
            .with_context(skip_sku_check=True)
            .create({"name": "Test Bypass", "default_code": invalid_sku, "type": "consu"})
        )
        self.assertEqual(product.default_code, invalid_sku)

    def test_sku_validation_boundary_4_digit(self) -> None:
        valid_skus = ["1000", "9999"]
        for sku in valid_skus:
            with self.subTest(sku=sku):
                product = self.env["product.template"].create({"name": f"Test Product {sku}", "default_code": sku, "type": "consu"})
                self.assertEqual(product.default_code, sku)
                product.unlink()

        invalid_skus = ["999"]
        self._assert_sku_validation_error(invalid_skus)

    def test_sku_validation_boundary_8_digit(self) -> None:
        valid_skus = ["10000000", "99999999"]
        for sku in valid_skus:
            with self.subTest(sku=sku):
                product = self.env["product.template"].create({"name": f"Test Product {sku}", "default_code": sku, "type": "consu"})
                self.assertEqual(product.default_code, sku)
                product.unlink()

        invalid_skus = ["100000000"]
        self._assert_sku_validation_error(invalid_skus)

    def test_sku_validation_edge_cases(self) -> None:
        # Use factory which handles SKU generation properly
        product = ProductFactory.create(self.env, name="Test Empty SKU", default_code="", type="consu")
        self.assertIsNotNone(product.default_code, "Empty SKU should auto-generate for consumable products")
        self.assertNotEqual(product.default_code, "", "Auto-generated SKU should not be empty")
        # Factory generates SKUs in the correct format
        self.assertTrue(product.default_code, "Product should have a SKU")
        product.unlink()

        # Test with None SKU - factory will generate one
        product = ProductFactory.create(self.env, name="Test None SKU", type="consu")
        self.assertIsNotNone(product.default_code, "None SKU should auto-generate for consumable products")
        self.assertTrue(product.default_code, "Product should have a SKU")
        product.unlink()

        unique_sku_with_spaces = f"  {secrets.randbelow(9000) + 1000}  "
        with self.assertRaises(ValidationError) as context:
            self.env["product.template"].create(
                {"name": "Test Whitespace SKU", "default_code": unique_sku_with_spaces, "type": "consu"}
            )
        self.assertIn("SKU must be 4-8 digits", str(context.exception))

        unique_sku_with_zeros = f"000{secrets.randbelow(9000) + 1000}"
        product = self.env["product.template"].create(
            {"name": "Test Leading Zeros", "default_code": unique_sku_with_zeros, "type": "consu"}
        )
        self.assertEqual(product.default_code, unique_sku_with_zeros)
        product.unlink()

    def test_is_scrap_field_default_value(self) -> None:
        product = ProductFactory.create(self.env, name="Test Scrap Product", type="consu")
        self.assertFalse(product.is_scrap, "is_scrap should default to False")

    def test_is_scrap_field_can_be_set(self) -> None:
        product = ProductFactory.create(self.env, name="Test Scrap Product", type="consu")
        product.is_scrap = True
        self.assertTrue(product.is_scrap, "is_scrap should be True after setting")

    def test_motor_product_creation(self) -> None:
        product = MotorFactory.create(self.env, name="Test Motor Product", motor_hp=100)

        self.assertTrue(product.exists())
        self.assertEqual(product.motor.horsepower, 100)
        self.assertTrue(product.motor.serial_number)
        self.assertTrue(product.default_code)

    def test_product_scrap_field_basic(self) -> None:
        product = ProductFactory.create(self.env, name="Test Scrap Product", type="consu")

        if hasattr(product, "is_scrap"):
            self.assertFalse(product.is_scrap, "is_scrap should default to False")

            product.is_scrap = True
            self.assertTrue(product.is_scrap, "is_scrap should be True after setting")
        else:
            self.skipTest("is_scrap field not available in current model")

    def test_name_field_validation(self) -> None:
        product = ProductFactory.create(self.env, name="", type="consu")
        self.assertEqual(product.name, "", "Empty string name should be allowed")
        product.unlink()

        product = ProductFactory.create(self.env, name="Test Product Name", type="consu")
        self.assertEqual(product.name, "Test Product Name")

        product.name = "Updated Product Name"
        self.assertEqual(product.name, "Updated Product Name")

        product.name = ""
        self.assertEqual(product.name, "", "Setting name to empty string should be allowed")

        # Test that creating a product without a name raises an IntegrityError
        with self.assertRaises(psycopg2.IntegrityError) as context:
            # Use a unique SKU to avoid database collisions
            test_sku = generate_unique_sku()
            self.env["product.template"].create({"default_code": test_sku, "type": "consu"})
        self.assertIn("null value", str(context.exception).lower())
