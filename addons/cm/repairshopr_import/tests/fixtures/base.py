from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "RepairshoprImporter": "repairshopr.importer",
        "ProductTemplate": "product.template",
        "Partner": "res.partner",
    }

    @property
    def RepairshoprImporter(self) -> "odoo.model.repairshopr_importer":
        return self.env["repairshopr.importer"]

    @property
    def ProductTemplate(self) -> "odoo.model.product_template":
        return self.env["product.template"]

    @property
    def Partner(self) -> "odoo.model.res_partner":
        return self.env["res.partner"]
