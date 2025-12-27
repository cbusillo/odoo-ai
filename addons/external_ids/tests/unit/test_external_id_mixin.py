from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ExternalSystemFactory


@tagged(*UNIT_TAGS)
class TestExternalIdMixin(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.discord_system = ExternalSystemFactory.create(
            self.env,
            name="Discord",
            code="discord",
        )
        self.shopify_system = ExternalSystemFactory.create(
            self.env,
            name="Shopify",
            code="shopify",
        )

    def test_set_and_get_external_id_on_partner(self) -> None:
        partner = self.Partner.create({"name": "Mixin Test Partner"})

        success = partner.set_external_id("discord", "123456789012345678")
        self.assertTrue(success)

        external_id = partner.get_external_system_id("discord")
        self.assertEqual(external_id, "123456789012345678")

    def test_set_multiple_external_ids(self) -> None:
        partner = self.Partner.create({"name": "Multi ID Partner"})

        partner.set_external_id("discord", "987654321098765432")
        partner.set_external_id("shopify", "gid://shopify/Customer/123")

        self.assertEqual(partner.get_external_system_id("discord"), "987654321098765432")
        self.assertEqual(partner.get_external_system_id("shopify"), "gid://shopify/Customer/123")
        self.assertFalse(partner.get_external_system_id("nonexistent"))

    def test_update_existing_external_id(self) -> None:
        partner = self.Partner.create({"name": "Update Test"})

        partner.set_external_id("discord", "111111111111111111")
        self.assertEqual(partner.get_external_system_id("discord"), "111111111111111111")

        partner.set_external_id("discord", "222222222222222222")
        self.assertEqual(partner.get_external_system_id("discord"), "222222222222222222")

        discord_ids = self.ExternalId.search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
                ("system_id", "=", self.discord_system.id),
            ]
        )
        self.assertEqual(len(discord_ids), 1)

    def test_search_by_external_id(self) -> None:
        partner1 = self.Partner.create({"name": "Search Test 1"})
        partner2 = self.Partner.create({"name": "Search Test 2"})

        partner1.set_external_id("discord", "333333333333333333")
        partner2.set_external_id("discord", "444444444444444444")

        found = self.Partner.search_by_external_id("discord", "333333333333333333")
        self.assertEqual(found, partner1)

        not_found = self.Partner.search_by_external_id("discord", "999999999999999999")
        self.assertFalse(not_found)

        invalid_system = self.Partner.search_by_external_id("invalid", "123")
        self.assertFalse(invalid_system)

    def test_action_view_external_ids(self) -> None:
        partner = self.Partner.create({"name": "View Test"})
        partner.set_external_id("discord", "666666666666666666")

        action = partner.action_view_external_ids()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "external.id")
        self.assertIn(("res_model", "=", "res.partner"), action["domain"])
        self.assertIn(("res_id", "=", partner.id), action["domain"])
        self.assertEqual(action["context"]["default_res_model"], "res.partner")
        self.assertEqual(action["context"]["default_res_id"], partner.id)

    def test_external_id_on_employee(self) -> None:
        employee = self.Employee.create(
            {
                "name": "Test Employee",
                "work_email": "employee@example.com",
            }
        )

        employee.set_external_id("discord", "777777777777777777")
        self.assertEqual(employee.get_external_system_id("discord"), "777777777777777777")

        found = self.Employee.search_by_external_id("discord", "777777777777777777")
        self.assertEqual(found, employee)

    def test_external_id_on_product(self) -> None:
        product = self.Product.create(
            {
                "name": "Test Product",
                "default_code": "PROD-001",
            }
        )

        product.set_external_id("shopify", "gid://shopify/Product/123456")
        self.assertEqual(product.get_external_system_id("shopify"), "gid://shopify/Product/123456")

        found = self.Product.search_by_external_id("shopify", "gid://shopify/Product/123456")
        self.assertEqual(found, product)

    def test_set_external_id_invalid_system(self) -> None:
        partner = self.Partner.create({"name": "Invalid System Test"})

        with self.assertRaises(ValueError) as context:
            partner.set_external_id("nonexistent_system", "123")

        self.assertIn("not found", str(context.exception))

    def test_inactive_external_ids_not_returned(self) -> None:
        partner = self.Partner.create({"name": "Inactive Test"})

        self.ExternalId.create(
            {
                "res_model": "res.partner",
                "res_id": partner.id,
                "system_id": self.discord_system.id,
                "external_id": "888888888888888888",
                "active": False,
            }
        )

        result = partner.get_external_system_id("discord")
        self.assertFalse(result)
