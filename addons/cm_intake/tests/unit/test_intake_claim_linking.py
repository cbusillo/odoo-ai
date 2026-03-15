from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestIntakeClaimLinking(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.partner = self.Partner.create({"name": "Claim District"})
        self.device_model = self.DeviceModel.create({"number": "Chromebook 3100"})
        self.device = self.Device.create(
            {
                "model": self.device_model.id,
                "owner": self.partner.id,
                "payer": self.partner.id,
            }
        )
        self.intake_order = self.IntakeOrder.create({"client": self.partner.id})

    def test_create_links_claim_number_to_canonical_claim(self) -> None:
        intake_device = self.IntakeOrderDevice.create(
            {
                "intake_order": self.intake_order.id,
                "device": self.device.id,
                "claim_number": "C-1001",
            }
        )

        self.assertEqual(intake_device.claim_number, "C-1001")
        self.assertTrue(intake_device.claim_id)
        self.assertEqual(intake_device.claim_id.claim_number, "C-1001")
        self.assertEqual(intake_device.claim_id.partner, self.partner)

    def test_create_reuses_existing_claim_for_same_partner(self) -> None:
        existing_claim = self.RepairClaim.create({"claim_number": "C-1002", "partner": self.partner.id})

        intake_device = self.IntakeOrderDevice.create(
            {
                "intake_order": self.intake_order.id,
                "device": self.device.id,
                "claim_number": "C-1002",
            }
        )

        self.assertEqual(intake_device.claim_id, existing_claim)

    def test_claim_id_write_keeps_denormalized_claim_number_in_sync(self) -> None:
        intake_device = self.IntakeOrderDevice.create(
            {
                "intake_order": self.intake_order.id,
                "device": self.device.id,
            }
        )
        claim = self.RepairClaim.create({"claim_number": "C-1003", "partner": self.partner.id})

        intake_device.write({"claim_id": claim.id})

        self.assertEqual(intake_device.claim_id, claim)
        self.assertEqual(intake_device.claim_number, "C-1003")
