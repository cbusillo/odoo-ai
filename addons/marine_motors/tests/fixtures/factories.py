import random

from odoo.api import Environment

from test_support.tests.base_types import OdooValue
from test_support.tests.fixtures.factories import PartnerFactory, ProductFactory, SaleOrderFactory
from test_support.tests.test_helpers import generate_motor_serial, generate_unique_name, generate_unique_sku


def _get_motor_manufacturer(environment: Environment) -> "odoo.model.product_manufacturer":
    manufacturer = environment["product.manufacturer"].search([("is_motor_manufacturer", "=", True)], limit=1)
    if not manufacturer:
        manufacturer = environment["product.manufacturer"].create(
            {
                "name": "Test Motor Manufacturer",
                "is_motor_manufacturer": True,
            }
        )
    return manufacturer


def _get_motor_stroke(environment: Environment) -> "odoo.model.motor_stroke":
    stroke = environment["motor.stroke"].search([], limit=1)
    if not stroke:
        stroke = environment["motor.stroke"].sudo().create({"name": "4-Stroke", "code": "4"})
    return stroke


def _get_motor_configuration(environment: Environment) -> "odoo.model.motor_configuration":
    configuration = environment["motor.configuration"].search([], limit=1)
    if not configuration:
        configuration = environment["motor.configuration"].sudo().create({"name": "V6", "code": "V6"})
    return configuration


class MotorFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.product_template":
        manufacturer = _get_motor_manufacturer(environment)
        stroke = _get_motor_stroke(environment)
        configuration = _get_motor_configuration(environment)

        motor_field_mapping = {
            "motor_hp": "horsepower",
            "motor_year": "year",
            "motor_model": "model",
            "motor_serial": "serial_number",
            "location": "location",
            "cost": "cost",
        }

        motor_kwargs = {}
        product_kwargs = {}
        for key, value in kwargs.items():
            if key in motor_field_mapping:
                motor_kwargs[motor_field_mapping[key]] = value
            else:
                product_kwargs[key] = value

        motor_values = {
            "horsepower": motor_kwargs.get("horsepower", random.choice([25, 40, 60, 75, 90, 115, 150])),
            "year": motor_kwargs.get("year", random.randint(2015, 2024)),
            "model": motor_kwargs.get("model", f"Model-{random.choice(['X', 'Y', 'Z'])}{random.randint(100, 999)}"),
            "serial_number": motor_kwargs.get("serial_number", generate_motor_serial()),
            "motor_number": generate_unique_sku(),
            "manufacturer": manufacturer.id,
            "stroke": stroke.id,
            "configuration": configuration.id,
        }
        if "location" in motor_kwargs:
            motor_values["location"] = motor_kwargs["location"]
        if "cost" in motor_kwargs:
            motor_values["cost"] = motor_kwargs["cost"]

        motor_record = environment["motor"].create(motor_values)
        product_name = product_kwargs.pop("name", generate_unique_name("Test Motor"))

        return ProductFactory.create(
            environment,
            name=product_name,
            default_code=motor_values["motor_number"],
            type="consu",
            list_price=2500.0,
            standard_price=1500.0,
            weight=150.0,
            volume=0.5,
            motor=motor_record.id,
            source=product_kwargs.pop("source", "motor"),
            **product_kwargs,
        )


class ProductTypeFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.product_type":
        defaults = {
            "name": generate_unique_name("Test Product Type"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return environment["product.type"].create(defaults)


class MotorProductTemplateFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.motor_product_template":
        part_type = kwargs.get("part_type")
        if not part_type:
            part_type = ProductTypeFactory.create(environment)
            kwargs["part_type"] = part_type.id
        elif hasattr(part_type, "id"):
            kwargs["part_type"] = getattr(part_type, "id")

        defaults = {
            "name": generate_unique_name("Test Motor Template"),
            "initial_quantity": 1.0,
            "bin": f"BIN-{random.randint(100, 999)}",
            "weight": random.uniform(1.0, 50.0),
            "include_year_in_name": True,
            "include_hp_in_name": True,
            "include_model_in_name": False,
            "include_oem_in_name": False,
            "is_quantity_listing": False,
            "year_from": random.randint(1990, 2015) if random.choice([True, False]) else None,
            "year_to": random.randint(2016, 2024) if random.choice([True, False]) else None,
        }
        defaults.update(kwargs)

        if defaults.get("year_from") and defaults.get("year_to") and defaults["year_from"] > defaults["year_to"]:
            defaults["year_from"], defaults["year_to"] = defaults["year_to"], defaults["year_from"]

        return environment["motor.product.template"].create(defaults)

    @staticmethod
    def create_with_filters(environment: Environment, **kwargs: OdooValue) -> "odoo.model.motor_product_template":
        stroke = _get_motor_stroke(environment)
        configuration = _get_motor_configuration(environment)
        manufacturer = _get_motor_manufacturer(environment)

        defaults = {
            "strokes": [(6, 0, [stroke.id])],
            "configurations": [(6, 0, [configuration.id])],
            "manufacturers": [(6, 0, [manufacturer.id])],
        }
        defaults.update(kwargs)

        return MotorProductTemplateFactory.create(environment, **defaults)


class MotorStrokeFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.motor_stroke":
        defaults = {
            "name": kwargs.get("name", "4-Stroke"),
            "code": kwargs.get("code", "4"),
        }
        defaults.update(kwargs)
        return environment["motor.stroke"].sudo().create(defaults)


class MotorConfigurationFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.motor_configuration":
        defaults = {
            "name": kwargs.get("name", "V6"),
            "code": kwargs.get("code", "V6"),
        }
        defaults.update(kwargs)
        return environment["motor.configuration"].sudo().create(defaults)


__all__ = [
    "MotorConfigurationFactory",
    "MotorFactory",
    "MotorProductTemplateFactory",
    "MotorStrokeFactory",
    "PartnerFactory",
    "ProductFactory",
    "ProductTypeFactory",
    "SaleOrderFactory",
]
