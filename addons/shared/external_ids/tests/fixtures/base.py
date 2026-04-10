from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "ExternalSystem": "external.system",
        "ExternalId": "external.id",
        "FixtureRecord": "external.id.fixture",
        "Partner": "res.partner",
    }

    @property
    def ExternalSystem(self) -> "odoo.model.external_system":
        return self.env["external.system"]

    @property
    def ExternalId(self) -> "odoo.model.external_id":
        return self.env["external.id"]

    @property
    def FixtureRecord(self) -> "odoo.model.external_id_fixture":
        return self.env["external.id.fixture"]

    @property
    def Partner(self) -> "odoo.model.res_partner":
        return self.env["res.partner"]
