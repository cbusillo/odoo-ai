from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "CmDataImporter": "integration.cm_data.importer",
    }

    @property
    def CmDataImporter(self) -> "odoo.model.integration_cm_data_importer":
        return self.env["integration.cm_data.importer"]
