from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "AuthentikMapping": "authentik.sso.group.mapping",
        "Users": "res.users",
    }

    @property
    def AuthentikMapping(self) -> "odoo.model.authentik_sso_group_mapping":
        return self.env["authentik.sso.group.mapping"]

    @property
    def Users(self) -> "odoo.model.res_users":
        return self.env["res.users"]
