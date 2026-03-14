from datetime import datetime

from ...services.cm_data_client import CmDataAccountName
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _account_row(
    *,
    record_id: int,
    account_name: str,
    ticket_name: str | None = None,
    ticket_name_report: str | None = None,
) -> CmDataAccountName:
    return CmDataAccountName(
        record_id=record_id,
        account_name=account_name,
        ticket_name=ticket_name,
        ticket_name_report=ticket_name_report,
        label_names=None,
        claim_name_list=None,
        multi_building_flag=False,
        price_list=None,
        price_list_2=None,
        priority_flag=False,
        on_delivery_schedule=False,
        shipping_enable=False,
        location_drop=None,
        updated_at=datetime(2026, 3, 14, 9, 0, 0),
    )


@common.tagged(*common.UNIT_TAGS)
class TestAccountPartnerLookup(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.CmDataImporter

    def test_build_account_partner_lookup_map_prefers_exact_account_name(self) -> None:
        account_rows = [
            _account_row(
                record_id=107,
                account_name="Riverhead",
                ticket_name="Riverhead",
                ticket_name_report="Riverhead",
            ),
            _account_row(
                record_id=108,
                account_name="Riverhead (Dropoff)",
                ticket_name="Riverhead",
                ticket_name_report="Riverhead",
            ),
        ]

        partner_lookup_map = self.importer._build_account_partner_lookup_map(
            account_rows,
            {
                107: 595,
                108: 596,
            },
        )

        self.assertEqual(self.importer._resolve_account_partner_id("Riverhead", partner_lookup_map), 595)

    def test_resolve_account_partner_id_supports_trailing_the_variant(self) -> None:
        partner_lookup_map = self.importer._build_account_partner_lookup_map(
            [
                _account_row(
                    record_id=11,
                    account_name="The Brearley School",
                    ticket_name="Brearley",
                    ticket_name_report="Brearley",
                )
            ],
            {11: 621},
        )

        self.assertEqual(self.importer._resolve_account_partner_id("Brearley School, The", partner_lookup_map), 621)

    def test_resolve_account_partner_id_supports_hyphenated_location_stem(self) -> None:
        partner_lookup_map = self.importer._build_account_partner_lookup_map(
            [
                _account_row(
                    record_id=93,
                    account_name="Northport-E. Northport",
                    ticket_name="Northport HS",
                    ticket_name_report="Northport HS",
                )
            ],
            {93: 578},
        )

        self.assertEqual(self.importer._resolve_account_partner_id("Northport", partner_lookup_map), 578)

    def test_resolve_account_partner_id_supports_uppercase_duplicate_letter_typos(self) -> None:
        partner_lookup_map = self.importer._build_account_partner_lookup_map(
            [
                _account_row(
                    record_id=154,
                    account_name="WSBOCES",
                    ticket_name="WSBOCES",
                    ticket_name_report="WSBOCES",
                )
            ],
            {154: 643},
        )

        self.assertEqual(self.importer._resolve_account_partner_id("WSBOOCES", partner_lookup_map), 643)
