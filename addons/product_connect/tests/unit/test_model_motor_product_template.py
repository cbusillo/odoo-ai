from odoo import fields
from odoo.exceptions import ValidationError
from ..common_imports import tagged, UNIT_TAGS

from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestMotorProductTemplate(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.MotorProductTemplate = self.env["motor.product.template"]
        self.Motor = self.env["motor"]

        self.manufacturer = self.env["product.manufacturer"].create({"name": "Test Manufacturer", "is_motor_manufacturer": True})

        self.stroke = self.env["motor.stroke"].sudo().create({"name": "4-Stroke", "code": "4"})

        self.configuration = self.env["motor.configuration"].sudo().create({"name": "V6", "code": "V6"})

        self.part_type = self.env["product.type"].create({"name": "Test Part Type"})

    def test_year_range_validation(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            self.MotorProductTemplate.create(
                {"name": "Test Template", "year_from": 2020, "year_to": 2010, "part_type": self.part_type.id}
            )
        self.assertIn("cannot be greater than", str(cm.exception))

    def test_year_range_max_validation(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            self.MotorProductTemplate.create(
                {"name": "Test Template", "year_from": 1920, "year_to": 2025, "part_type": self.part_type.id}
            )
        self.assertIn("Year From must be between", str(cm.exception))

    def test_year_range_min_validation(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            self.MotorProductTemplate.create({"name": "Test Template", "year_from": 1899, "part_type": self.part_type.id})
        self.assertIn("Year From must be between", str(cm.exception))

    def test_year_range_future_validation(self) -> None:
        current_year = fields.Date.today().year
        with self.assertRaises(ValidationError) as cm:
            self.MotorProductTemplate.create({"name": "Test Template", "year_to": current_year + 10, "part_type": self.part_type.id})
        self.assertIn("Year To must be between", str(cm.exception))

    def test_year_range_display_both_years(self) -> None:
        template = self.MotorProductTemplate.create(
            {"name": "Test Template", "year_from": 2010, "year_to": 2020, "part_type": self.part_type.id}
        )
        self.assertEqual(template.year_range_display, "2010 - 2020")

    def test_year_range_display_only_from(self) -> None:
        template = self.MotorProductTemplate.create({"name": "Test Template", "year_from": 2010, "part_type": self.part_type.id})
        self.assertEqual(template.year_range_display, "2010 - Present")

    def test_year_range_display_only_to(self) -> None:
        template = self.MotorProductTemplate.create({"name": "Test Template", "year_to": 2020, "part_type": self.part_type.id})
        self.assertEqual(template.year_range_display, "Up to 2020")

    def test_year_range_display_no_years(self) -> None:
        template = self.MotorProductTemplate.create({"name": "Test Template", "part_type": self.part_type.id})
        self.assertEqual(template.year_range_display, "All Years")

    def test_get_motors_for_template_year_filtering(self) -> None:
        template = self.MotorProductTemplate.create(
            {
                "name": "Test Template",
                "year_from": 2015,
                "year_to": 2020,
                "part_type": self.part_type.id,
                "strokes": [(6, 0, [self.stroke.id])],
                "configurations": [(6, 0, [self.configuration.id])],
                "manufacturers": [(6, 0, [self.manufacturer.id])],
            }
        )

        motor_2010 = self.Motor.create(
            {
                "year": "2010",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model 2010",
            }
        )

        motor_2015 = self.Motor.create(
            {
                "year": "2015",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model 2015",
            }
        )

        motor_2018 = self.Motor.create(
            {
                "year": "2018",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model 2018",
            }
        )

        motor_2025 = self.Motor.create(
            {
                "year": "2025",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model 2025",
            }
        )

        matching_motors = template._get_motors_for_template()

        self.assertIn(motor_2015, matching_motors)
        self.assertIn(motor_2018, matching_motors)
        self.assertNotIn(motor_2010, matching_motors)
        self.assertNotIn(motor_2025, matching_motors)

    def test_get_motors_for_template_no_year_range(self) -> None:
        template = self.MotorProductTemplate.create(
            {
                "name": "Test Template",
                "part_type": self.part_type.id,
                "strokes": [(6, 0, [self.stroke.id])],
                "configurations": [(6, 0, [self.configuration.id])],
                "manufacturers": [(6, 0, [self.manufacturer.id])],
            }
        )

        motor_2010 = self.Motor.create(
            {
                "year": "2010",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model",
            }
        )

        motor_2025 = self.Motor.create(
            {
                "year": "2025",
                "horsepower": 100,
                "stroke": self.stroke.id,
                "configuration": self.configuration.id,
                "manufacturer": self.manufacturer.id,
                "currency_id": self.env.ref("base.USD").id,
                "model": "Test Model",
            }
        )

        matching_motors = template._get_motors_for_template()

        self.assertIn(motor_2010, matching_motors)
        self.assertIn(motor_2025, matching_motors)
