import base64

from ..common_imports import tagged, ValidationError, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import MotorFactory


@tagged(*UNIT_TAGS)
class TestMotor(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.stage = self.env["motor.stage"].create({"name": "Checkin"})
        motor_product = MotorFactory.create(self.env)
        self.test_motor = motor_product.motor

    def _create_test_motor(self, **extra: int | float | str) -> "odoo.model.motor":
        factory_params = {}
        motor_field_mapping = {
            "horsepower": "motor_hp",
            "year": "motor_year",
            "model": "motor_model",
            "serial_number": "motor_serial",
            "location": "location",
            "cost": "cost",
        }
        for key, value in extra.items():
            mapped_key = motor_field_mapping.get(key, key)
            factory_params[mapped_key] = value

        product = MotorFactory.create(self.env, **factory_params)
        return product.motor

    def test_get_horsepower_formatted(self) -> None:
        motor = self._create_test_motor(horsepower=100.0)
        self.assertEqual(motor.get_horsepower_formatted(), "100 HP")
        motor.horsepower = 100.5
        self.assertEqual(motor.get_horsepower_formatted(), "100.5 HP")

    def test_sanitize_vals(self) -> None:
        result = self.env["motor"]._sanitize_vals({"model": "abc", "serial_number": "sn1"})
        self.assertEqual(result["model"], "ABC")
        self.assertEqual(result["serial_number"], "SN1")

    def test_unique_location(self) -> None:
        self._create_test_motor(location="A1")
        with self.assertRaises(ValidationError):
            self._create_test_motor(location="A1")

    def test_generate_qr_code(self) -> None:
        motor = self._create_test_motor()
        code = motor.generate_qr_code()
        self.assertTrue(code)
        base64.b64decode(code)

    def test_create_motor_dependencies(self) -> None:
        product = MotorFactory.create(self.env)
        motor = product.motor

        self.assertTrue(motor.manufacturer)
        self.assertTrue(motor.stroke)

    def test_create_motor_products_year_filtering(self) -> None:
        motor_2010 = self._create_test_motor(year=2010, cost=100.0)
        motor_2018 = self._create_test_motor(year=2018, cost=100.0)
        motor_2025 = self._create_test_motor(year=2025, cost=100.0)

        template = self.env["motor.product.template"].create(
            {
                "name": "Year-Specific Part",
                "year_from": 2015,
                "year_to": 2020,
                "strokes": [(6, 0, [motor_2018.stroke.id])],
                "configurations": [(6, 0, [motor_2018.configuration.id])],
                "manufacturers": [(6, 0, [motor_2018.manufacturer.id])],
                "initial_quantity": 1,
                "part_type": self.env["product.type"].create({"name": "Test Type"}).id,
            }
        )

        (motor_2010 | motor_2018 | motor_2025).create_motor_products()

        products_2010_with_template = motor_2010.products.filtered(lambda p: p.motor_product_template == template)
        products_2018_with_template = motor_2018.products.filtered(lambda p: p.motor_product_template == template)
        products_2025_with_template = motor_2025.products.filtered(lambda p: p.motor_product_template == template)

        self.assertEqual(
            len(products_2010_with_template), 0, "Motor from 2010 should not have products from this template (before year range)"
        )
        self.assertEqual(
            len(products_2018_with_template), 1, "Motor from 2018 should have 1 product from this template (within year range)"
        )
        self.assertEqual(
            len(products_2025_with_template), 0, "Motor from 2025 should not have products from this template (after year range)"
        )

    def test_create_motor_products_no_year_range(self) -> None:
        motor_2010 = self._create_test_motor(year=2010, cost=100.0)
        motor_2025 = self._create_test_motor(year=2025, cost=100.0)

        template = self.env["motor.product.template"].create(
            {
                "name": "Universal Part",
                "strokes": [(6, 0, [motor_2010.stroke.id])],
                "configurations": [(6, 0, [motor_2010.configuration.id])],
                "manufacturers": [(6, 0, [motor_2010.manufacturer.id])],
                "initial_quantity": 1,
                "part_type": self.env["product.type"].create({"name": "Test Type"}).id,
            }
        )

        (motor_2010 | motor_2025).create_motor_products()

        products_2010_with_template = motor_2010.products.filtered(lambda p: p.motor_product_template == template)
        products_2025_with_template = motor_2025.products.filtered(lambda p: p.motor_product_template == template)

        self.assertEqual(len(products_2010_with_template), 1, "Motor from 2010 should have the universal product from this template")
        self.assertEqual(len(products_2025_with_template), 1, "Motor from 2025 should have the universal product from this template")

    def test_create_motor_product_generation(self) -> None:
        product = MotorFactory.create(self.env)
        motor = product.motor

        self.assertTrue(motor)
        self.assertGreater(motor.horsepower, 0)
        self.assertTrue(motor.model)
        self.assertTrue(motor.serial_number)

        custom_product = MotorFactory.create(self.env, motor_hp=150, motor_year=2023, motor_model="CUSTOM-MODEL")
        custom_motor = custom_product.motor
        self.assertEqual(custom_motor.horsepower, 150)
        self.assertEqual(custom_motor.year, "2023")
        self.assertEqual(custom_motor.model, "CUSTOM-MODEL")

    def test_motor_factory_creation(self) -> None:
        product1 = MotorFactory.create(self.env, motor_hp=100)
        product2 = MotorFactory.create(self.env, motor_hp=120)

        motor1 = product1.motor
        motor2 = product2.motor

        self.assertNotEqual(motor1.id, motor2.id)
        self.assertNotEqual(motor1.motor_number, motor2.motor_number)
        self.assertNotEqual(motor1.serial_number, motor2.serial_number)

        self.assertEqual(motor1.horsepower, 100)
        self.assertEqual(motor2.horsepower, 120)
        self.assertTrue(motor1.model)
        self.assertTrue(motor2.model)
