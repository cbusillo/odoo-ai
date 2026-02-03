from ..common_imports import tagged, ValidationError, UNIT_TAGS
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ExternalSystemFactory, ExternalIdFactory


@tagged(*UNIT_TAGS)
class TestExternalId(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.discord_system = ExternalSystemFactory.create(
            self.env,
            name="Discord",
            code="discord",
            id_format=r"^\d{18}$",
            reuse_existing=True,
        )
        self.shopify_system = ExternalSystemFactory.create(
            self.env,
            name="Shopify",
            code="shopify",
            id_prefix="gid://shopify/Customer/",
            reuse_existing=True,
        )

    def test_create_external_id(self) -> None:
        partner = self.Partner.create({"name": "John Doe"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="123456789012345678",
        )

        self.assertEqual(external_id.res_model, "res.partner")
        self.assertEqual(external_id.res_id, partner.id)
        self.assertEqual(external_id.external_id, "123456789012345678")
        self.assertTrue(external_id.active)

    def test_compute_reference(self) -> None:
        partner = self.Partner.create({"name": "Test Partner"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="987654321098765432",
        )

        self.assertEqual(external_id.reference, partner)

    def test_inverse_reference(self) -> None:
        partner = self.Partner.create({"name": "Reference Test"})
        external_id = self.ExternalId.create(
            {
                "system_id": self.discord_system.id,
                "external_id": "111111111111111111",
                "reference": partner,
            }
        )

        self.assertEqual(external_id.res_model, "res.partner")
        self.assertEqual(external_id.res_id, partner.id)

    def test_compute_display_name(self) -> None:
        partner = self.Partner.create({"name": "Display Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.shopify_system.id,
            external_id="7654321",
        )

        expected_name = f"Shopify: gid://shopify/Customer/7654321 (Display Test)"
        self.assertEqual(external_id.display_name, expected_name)

    def test_compute_record_name(self) -> None:
        partner = self.Partner.create({"name": "Record Name Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="222222222222222222",
        )

        self.assertEqual(external_id.record_name, "Record Name Test")

        partner.unlink()
        external_id._compute_record_name()
        self.assertEqual(external_id.record_name, "[Deleted res.partner]")

    def test_id_format_validation(self) -> None:
        partner = self.Partner.create({"name": "Validation Test"})

        with self.assertRaises(ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="res.partner",
                res_id=partner.id,
                system_id=self.discord_system.id,
                external_id="invalid-format",
            )

    def test_unique_external_id_per_system(self) -> None:
        partner1 = self.Partner.create({"name": "Partner 1"})
        partner2 = self.Partner.create({"name": "Partner 2"})

        ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner1.id,
            system_id=self.discord_system.id,
            external_id="333333333333333333",
        )

        with self.assertRaises(ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="res.partner",
                res_id=partner2.id,
                system_id=self.discord_system.id,
                external_id="333333333333333333",
            )

    def test_unique_record_per_system(self) -> None:
        partner = self.Partner.create({"name": "Unique Test"})

        ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="444444444444444444",
        )

        with self.assertRaises(ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="res.partner",
                res_id=partner.id,
                system_id=self.discord_system.id,
                external_id="555555555555555555",
            )

    def test_get_record_by_external_id(self) -> None:
        partner = self.Partner.create({"name": "Lookup Test"})
        ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="666666666666666666",
        )

        found_record = self.ExternalId.get_record_by_external_id("discord", "666666666666666666")
        self.assertEqual(found_record, partner)

        not_found = self.ExternalId.get_record_by_external_id("discord", "999999999999999999")
        self.assertIsNone(not_found)

        not_found_system = self.ExternalId.get_record_by_external_id("invalid_system", "123")
        self.assertIsNone(not_found_system)

    def test_action_sync(self) -> None:
        partner = self.Partner.create({"name": "Sync Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="777777777777777777",
        )

        self.assertFalse(external_id.last_sync)
        result = external_id.action_sync()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertTrue(external_id.last_sync)

    def test_unlink_except_active(self) -> None:
        partner = self.Partner.create({"name": "Delete Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="res.partner",
            res_id=partner.id,
            system_id=self.discord_system.id,
            external_id="888888888888888888",
        )

        with self.assertRaises(ValidationError):
            external_id.unlink()

        external_id.active = False
        external_id.unlink()

    def test_reference_models_selection(self) -> None:
        models = self.ExternalId._reference_models()
        model_names = [m[0] for m in models]

        self.assertIn("hr.employee", model_names)
        self.assertIn("res.partner", model_names)
        self.assertIn("product.product", model_names)
