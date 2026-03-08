from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "Overrides": "environment.overrides",
    }

    @property
    def Overrides(self) -> "odoo.model.environment_overrides":
        return self.env["environment.overrides"]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ConfigParameter = cls.env["ir.config_parameter"].sudo()
