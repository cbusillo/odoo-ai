from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import MotorFactory


@tagged(*UNIT_TAGS)
class TestMotorWorkflow(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()

    def test_motor_creation(self) -> None:
        product = MotorFactory.create(self.env, motor_hp=200, motor_year=2024, motor_model="Test Model")
        motor = product.motor

        self.assertTrue(motor.exists())
        self.assertEqual(motor.horsepower, 200)
        self.assertEqual(motor.year, "2024")
        self.assertEqual(motor.model, "TEST MODEL")
        self.assertTrue(motor.serial_number)

    def test_motor_product_creation(self) -> None:
        motor = MotorFactory.create(self.env, motor_hp=150, motor_year=2023, motor_model="Product Test")

        self.assertTrue(motor.exists())
        self.assertEqual(motor.type, "consu")
        self.assertGreater(motor.list_price, 0)
        self.assertTrue(motor.default_code)

    def test_motor_product_enabling(self) -> None:
        motor = MotorFactory.create(self.env, motor_hp=175, motor_year=2023, motor_model="Enable Test")

        self.assertTrue(motor.sale_ok)
        self.assertTrue(motor.purchase_ok)

        motor.write({"sale_ok": False})
        self.assertFalse(motor.sale_ok)

        motor.write({"sale_ok": True})
        self.assertTrue(motor.sale_ok)

        motor.write({"purchase_ok": False})
        self.assertFalse(motor.purchase_ok)

        motor.write({"purchase_ok": True})
        self.assertTrue(motor.purchase_ok)
