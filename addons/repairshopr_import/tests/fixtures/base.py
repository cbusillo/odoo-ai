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
        cls.RepairshoprImporter = cls.env["repairshopr.importer"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.Partner = cls.env["res.partner"]
