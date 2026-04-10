from odoo.addons.cm_device.utils import clean_identifier_value

from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestIdentifierCleaning(UnitTestCase):
    def test_clean_identifier_value_normalizes_imei_digits(self) -> None:
        cleaned = clean_identifier_value(" 35-1234 5678 90123 ", identifier_type="imei")

        self.assertEqual(cleaned, "351234567890123")

    def test_clean_identifier_value_rejects_placeholder_tokens(self) -> None:
        cleaned = clean_identifier_value("unknown", identifier_type="serial")

        self.assertIsNone(cleaned)

    def test_clean_identifier_value_trims_serial_values(self) -> None:
        cleaned = clean_identifier_value("  A123  ", identifier_type="serial")

        self.assertEqual(cleaned, "A123")

    def test_extract_device_identifiers_uses_shared_cleaner_for_claim_and_po(self) -> None:
        identifiers = self.env["repairshopr.importer"]._extract_device_identifiers_from_line(
            "Serial: A123\nClaim: CLM-42\nPO:   PO-88\nIMEI: 35-1234-5678",
        )

        self.assertEqual(identifiers["claim"], "CLM-42")
        self.assertEqual(identifiers["po"], "PO-88")
