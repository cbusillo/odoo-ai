from __future__ import annotations

from datetime import datetime
from typing import cast

from ...services.cm_data_client import CmDataClient, CmDataContact
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _contact_row(
    *,
    record_id: int,
    account_name: str,
    sub_name: str | None,
    contact_notes: str | None,
) -> CmDataContact:
    return CmDataContact(
        record_id=record_id,
        account_name=account_name,
        sub_name=sub_name,
        contact_notes=contact_notes,
        sort_order=record_id,
        updated_at=datetime(2026, 3, 14, 9),
    )


class _ContactClientStub:
    def __init__(self, contact_rows: list[CmDataContact]) -> None:
        self._contact_rows = contact_rows

    def fetch_contacts(self, updated_at: datetime | None) -> list[CmDataContact]:
        assert updated_at is None
        return self._contact_rows


@common.tagged(*common.UNIT_TAGS)
class TestContactImport(UnitTestCase):
    def test_import_contacts_parses_contact_name_and_email_from_notes(self) -> None:
        importer = self.CmDataImporter
        system = importer._get_cm_data_system()
        account_partner = self.env["res.partner"].create({"name": "Eastern Suffolk BOCES"})

        importer._import_contacts(
            cast(
                CmDataClient,
                cast(
                    object,
                    _ContactClientStub(
                        [
                            _contact_row(
                                record_id=320,
                                account_name="WSBOOCES",
                                sub_name="POs",
                                contact_notes="Penny Notarnicola - pnotarni@wsboces.org",
                            )
                        ]
                    ),
                ),
            ),
            None,
            {importer._normalize_key("WSBOOCES"): account_partner.id},
            system,
            datetime(2026, 3, 14, 10),
        )

        contact_partner = self.env["res.partner"].search_by_external_id("cm_data", "320", resource="contact")

        self.assertEqual(contact_partner.name, "Penny Notarnicola")
        self.assertEqual(contact_partner.function, "POs")
        self.assertEqual(contact_partner.email, "pnotarni@wsboces.org")
        self.assertEqual(contact_partner.parent_id, account_partner)
        self.assertEqual(contact_partner.cm_data_contact_notes, "Penny Notarnicola - pnotarni@wsboces.org")

    def test_import_contacts_clears_stale_structured_fields_when_notes_do_not_parse(self) -> None:
        importer = self.CmDataImporter
        system = importer._get_cm_data_system()
        account_partner = self.env["res.partner"].create({"name": "The Buckley School"})
        contact_partner = self.env["res.partner"].create(
            {
                "name": "Edwin Gonzalez",
                "parent_id": account_partner.id,
                "type": "contact",
                "email": "egonzalez@buckleyschool.org",
                "function": "Pick Up",
            }
        )
        self.env["external.id"].sudo().create(
            {
                "system_id": system.id,
                "res_model": "res.partner",
                "res_id": contact_partner.id,
                "resource": "contact",
                "external_id": "143",
            }
        )

        importer._import_contacts(
            cast(
                CmDataClient,
                cast(
                    object,
                    _ContactClientStub(
                        [
                            _contact_row(
                                record_id=143,
                                account_name="Buckley School, The",
                                sub_name="Estimates, Pick Up",
                                contact_notes="Main district contact",
                            )
                        ]
                    ),
                ),
            ),
            None,
            {importer._normalize_key("Buckley School, The"): account_partner.id},
            system,
            datetime(2026, 3, 14, 10),
        )

        contact_partner.invalidate_recordset(["name", "email", "function", "cm_data_contact_notes"])

        self.assertEqual(contact_partner.name, "Estimates, Pick Up")
        self.assertFalse(contact_partner.email)
        self.assertFalse(contact_partner.function)
        self.assertEqual(contact_partner.cm_data_contact_notes, "Main district contact")
