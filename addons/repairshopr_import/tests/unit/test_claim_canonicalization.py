from ...services import repairshopr_sync_models as repairshopr_models
from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestClaimCanonicalization(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.RepairshoprImporter
        self.partner = self.Partner.create({"name": "Canonical Claim District"})

    def test_build_ticket_property_values_creates_claim_relation(self) -> None:
        ticket = repairshopr_models.Ticket(
            id=101,
            number=5001,
            properties=repairshopr_models.TicketProperties(claim_num="C-2001"),
        )

        values, identifiers = self.importer._build_ticket_property_values(ticket, partner=self.partner)

        self.assertIn("claim_id", values)
        claim_id_value = values["claim_id"]
        self.assertIsInstance(claim_id_value, int)
        claim = self.env["service.repair.claim"].browse(claim_id_value)
        self.assertEqual(claim.claim_number, "C-2001")
        self.assertEqual(claim.partner, self.partner)
        self.assertEqual(identifiers["ticket"], {"5001"})

    def test_build_ticket_property_values_reuses_partnerless_claim(self) -> None:
        claim = self.env["service.repair.claim"].create({"claim_number": "C-2002"})
        ticket = repairshopr_models.Ticket(
            id=102,
            properties=repairshopr_models.TicketProperties(claim_num="C-2002"),
        )

        values, _identifiers = self.importer._build_ticket_property_values(ticket, partner=self.partner)

        self.assertEqual(values["claim_id"], claim.id)
        claim.invalidate_recordset(["partner"])
        self.assertEqual(claim.partner, self.partner)
