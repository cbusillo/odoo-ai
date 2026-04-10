from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ExternalIdFactory, ExternalSystemFactory


@common.tagged(*common.UNIT_TAGS)
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
        fixture_record = self.FixtureRecord.create({"name": "John Doe"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="123456789012345678",
        )

        self.assertEqual(external_id.res_model, "external.id.fixture")
        self.assertEqual(external_id.res_id, fixture_record.id)
        self.assertEqual(external_id.external_id, "123456789012345678")
        self.assertTrue(external_id.active)

    def test_compute_reference(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Test Record"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="987654321098765432",
        )

        self.assertEqual(external_id.reference, fixture_record)

    def test_compute_reference_ignores_missing_model(self) -> None:
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.missing",
            res_id=999999,
            system_id=self.discord_system.id,
            external_id="123123123123123123",
        )

        external_id._compute_reference()

        self.assertFalse(external_id.reference)

    def test_inverse_reference(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Reference Test"})
        external_id = self.ExternalId.create(
            {
                "system_id": self.discord_system.id,
                "external_id": "111111111111111111",
                "reference": fixture_record,
            }
        )

        self.assertEqual(external_id.res_model, "external.id.fixture")
        self.assertEqual(external_id.res_id, fixture_record.id)

    def test_compute_display_name(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Display Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.shopify_system.id,
            external_id="7654321",
        )

        expected_name = f"Shopify: gid://shopify/Customer/7654321 (Display Test)"
        self.assertEqual(external_id.display_name, expected_name)

    def test_compute_record_name(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Record Name Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="222222222222222222",
        )

        self.assertEqual(external_id.record_name, "Record Name Test")

        fixture_record.unlink()
        external_id._compute_record_name()
        self.assertEqual(external_id.record_name, "[Deleted external.id.fixture]")

    def test_id_format_validation(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Validation Test"})

        with self.assertRaises(common.ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="external.id.fixture",
                res_id=fixture_record.id,
                system_id=self.discord_system.id,
                external_id="invalid-format",
            )

    def test_unique_external_id_per_system(self) -> None:
        first_record = self.FixtureRecord.create({"name": "Record 1"})
        second_record = self.FixtureRecord.create({"name": "Record 2"})

        ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=first_record.id,
            system_id=self.discord_system.id,
            external_id="333333333333333333",
        )

        with self.assertRaises(common.ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="external.id.fixture",
                res_id=second_record.id,
                system_id=self.discord_system.id,
                external_id="333333333333333333",
            )

    def test_unique_record_per_system(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Unique Test"})

        ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="444444444444444444",
        )

        with self.assertRaises(common.ValidationError):
            ExternalIdFactory.create(
                self.env,
                res_model="external.id.fixture",
                res_id=fixture_record.id,
                system_id=self.discord_system.id,
                external_id="555555555555555555",
            )

    def test_get_record_by_external_id(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Lookup Test"})
        ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            resource="default",
            external_id="666666666666666666",
        )

        found_record = self.ExternalId.get_record_by_external_id("discord", "666666666666666666")
        self.assertEqual(found_record, fixture_record)

        not_found = self.ExternalId.get_record_by_external_id("discord", "999999999999999999")
        self.assertIsNone(not_found)

        not_found_system = self.ExternalId.get_record_by_external_id("invalid_system", "123")
        self.assertIsNone(not_found_system)

    def test_action_open_reference(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Open Reference Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="777777777777777777",
        )

        result = external_id.action_open_reference()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "external.id.fixture")
        self.assertEqual(result["res_id"], fixture_record.id)

    def test_unlink_except_active(self) -> None:
        fixture_record = self.FixtureRecord.create({"name": "Delete Test"})
        external_id = ExternalIdFactory.create(
            self.env,
            res_model="external.id.fixture",
            res_id=fixture_record.id,
            system_id=self.discord_system.id,
            external_id="888888888888888888",
        )

        with self.assertRaises(common.ValidationError):
            external_id.unlink()

        external_id.active = False
        external_id.unlink()

    def test_reference_models_selection(self) -> None:
        models = self.ExternalId._reference_models()
        model_names = [m[0] for m in models]

        self.assertIn("external.id.fixture", model_names)
