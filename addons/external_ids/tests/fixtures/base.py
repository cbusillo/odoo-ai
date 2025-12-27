from odoo.tests import TransactionCase
from ..common_imports import DEFAULT_TEST_CONTEXT, UNIT_TAGS, tagged


@tagged(*UNIT_TAGS)
class UnitTestCase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_admin"))
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                **DEFAULT_TEST_CONTEXT,
            )
        )

    def setUp(self) -> None:
        super().setUp()
        self.ExternalSystem = self.env["external.system"]
        self.ExternalId = self.env["external.id"]
        self.Partner = self.env["res.partner"]
        self.Employee = self.env["hr.employee"]
        self.Product = self.env["product.product"]
