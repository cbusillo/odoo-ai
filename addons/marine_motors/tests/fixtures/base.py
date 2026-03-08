from typing import ClassVar

from test_support.tests.fixtures.base_cases import (
    SharedIntegrationTestCase,
    SharedTourTestCase,
    SharedUnitTestCase,
)

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(SharedUnitTestCase):
    pass


@common.tagged(*common.INTEGRATION_TAGS)
class IntegrationTestCase(SharedIntegrationTestCase):
    enforce_test_company_country = False


@common.tagged(*common.TOUR_TAGS)
class TourTestCase(SharedTourTestCase):
    reset_assets_per_database = True
    assets_reset_db_names: ClassVar[set[str]] = set()

    @classmethod
    def _ensure_required_domain_data(cls) -> None:
        manufacturer = cls.env["product.manufacturer"].search(
            [("is_motor_manufacturer", "=", True)],
            limit=1,
        )
        if not manufacturer:
            cls.env["product.manufacturer"].create(
                {
                    "name": "Test Motor Manufacturer",
                    "is_motor_manufacturer": True,
                }
            )

        stroke = cls.env["motor.stroke"].search([], limit=1)
        if not stroke:
            cls.env["motor.stroke"].create({"name": "4 Stroke"})

        configuration = cls.env["motor.configuration"].search([], limit=1)
        if not configuration:
            cls.env["motor.configuration"].create({"name": "V4"})

        color_tag = cls.env["product.color.tag"].search(
            [("name", "=", "Motors")],
            limit=1,
        )
        if not color_tag:
            color_tag = cls.env["product.color.tag"].create({"name": "Motors"})

        color = cls.env["product.color"].search(
            [("applicable_tags", "in", color_tag.id)],
            limit=1,
        )
        if not color:
            cls.env["product.color"].create(
                {
                    "name": "Test Color",
                    "color_code": "#123456",
                    "applicable_tags": [(6, 0, [color_tag.id])],
                }
            )
