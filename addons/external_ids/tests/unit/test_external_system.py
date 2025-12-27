from ..common_imports import tagged, ValidationError, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ExternalSystemFactory, ExternalIdFactory


@tagged(*UNIT_TAGS)
class TestExternalSystem(UnitTestCase):
    def test_create_external_system(self) -> None:
        system = ExternalSystemFactory.create(
            self.env,
            name="Discord",
            code="discord",
            description="Discord messaging system",
            url="https://discord.com",
            id_format=r"^\d{18}$",
            id_prefix="",
        )

        self.assertEqual(system.name, "Discord")
        self.assertEqual(system.code, "discord")
        self.assertTrue(system.active)
        self.assertEqual(system.id_format, r"^\d{18}$")

    def test_unique_code_constraint(self) -> None:
        ExternalSystemFactory.create(self.env, code="unique_code")

        with self.assertRaises(ValidationError):
            ExternalSystemFactory.create(self.env, code="unique_code")

    def test_unique_name_constraint(self) -> None:
        ExternalSystemFactory.create(self.env, name="Unique System")

        with self.assertRaises(ValidationError):
            ExternalSystemFactory.create(self.env, name="Unique System", code="different_code")

    def test_external_id_count(self) -> None:
        system = ExternalSystemFactory.create(self.env, name="Shopify", code="shopify")
        self.assertEqual(system.external_id_count, 0)

        partner = self.Partner.create({"name": "Test Customer"})
        ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=system.id,
            external_id="CUST-12345",
        )

        system._compute_external_id_count()
        self.assertEqual(system.external_id_count, 1)

    def test_archive_system(self) -> None:
        system = ExternalSystemFactory.create(self.env)
        self.assertTrue(system.active)

        system.active = False
        self.assertFalse(system.active)

        active_systems = self.ExternalSystem.search([("active", "=", True)])
        self.assertNotIn(system, active_systems)

    def test_system_with_external_ids_restriction(self) -> None:
        system = ExternalSystemFactory.create(self.env, name="RepairShopr", code="repairshopr")
        partner = self.Partner.create({"name": "Test Partner"})

        ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=system.id,
            external_id="RS-001",
        )

        with self.assertRaises(ValidationError):
            system.unlink()
