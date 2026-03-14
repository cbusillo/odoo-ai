from __future__ import annotations

from datetime import datetime
from typing import cast
from unittest import mock

from ...services.cm_data_client import CmDataAccountName, CmDataContact
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _account_row(*, record_id: int, account_name: str) -> CmDataAccountName:
    return CmDataAccountName(
        record_id=record_id,
        account_name=account_name,
        ticket_name=account_name,
        ticket_name_report=account_name,
        label_names=None,
        claim_name_list=None,
        multi_building_flag=False,
        price_list=None,
        price_list_2=None,
        priority_flag=False,
        on_delivery_schedule=False,
        shipping_enable=False,
        location_drop=None,
        updated_at=datetime(2026, 3, 14, 9),
    )


def _contact_row(*, record_id: int, account_name: str) -> CmDataContact:
    return CmDataContact(
        record_id=record_id,
        account_name=account_name,
        sub_name=f"Contact {record_id}",
        contact_notes=None,
        sort_order=record_id,
        updated_at=datetime(2026, 3, 14, 9),
    )


class _CmDataClientStub:
    def __init__(self, account_rows: list[CmDataAccountName], contact_rows: list[CmDataContact]) -> None:
        self._account_rows = account_rows
        self._contact_rows = contact_rows

    def __enter__(self) -> _CmDataClientStub:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def fetch_account_names(self, updated_at: datetime | None) -> list[CmDataAccountName]:
        del updated_at
        return self._account_rows

    def fetch_contacts(self, updated_at: datetime | None) -> list[CmDataContact]:
        del updated_at
        return self._contact_rows


@common.tagged(*common.UNIT_TAGS)
class TestValidationHealthSnapshot(UnitTestCase):
    def test_validation_health_snapshot_reports_complete_contact_coverage(self) -> None:
        importer = self.CmDataImporter
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_run_status", "success")
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_run_message", "")
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_run_at", "2026-03-14 18:02:02")
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_sync_at", "2026-03-14 18:00:00")

        system = self.env["external.system"].ensure_system(code="cm_data", name="CM Data")
        account_partner = self.env["res.partner"].create({"name": "Riverhead"})
        contact_partner = self.env["res.partner"].create({"name": "Contact 501", "parent_id": account_partner.id, "type": "contact"})
        self.env["external.id"].sudo().create(
            [
                {
                    "system_id": system.id,
                    "res_model": "res.partner",
                    "res_id": account_partner.id,
                    "resource": "account",
                    "external_id": "101",
                },
                {
                    "system_id": system.id,
                    "res_model": "res.partner",
                    "res_id": contact_partner.id,
                    "resource": "contact",
                    "external_id": "501",
                },
            ]
        )

        with mock.patch(
            "odoo.addons.cm_data_import.models.cm_data_importer.CmDataClient",
            return_value=_CmDataClientStub(
                account_rows=[_account_row(record_id=101, account_name="Riverhead")],
                contact_rows=[_contact_row(record_id=501, account_name="Riverhead")],
            ),
        ):
            snapshot = importer.get_validation_health_snapshot()
        metrics = cast(dict[str, object], snapshot["metrics"])
        samples = cast(dict[str, object], snapshot["samples"])

        self.assertTrue(snapshot["ok"])
        self.assertEqual(metrics["source_contact_count"], 1)
        self.assertEqual(metrics["missing_contact_external_id_count"], 0)
        self.assertEqual(metrics["distinct_unmatched_account_name_count"], 0)
        self.assertEqual(samples["missing_contact_external_ids_sample"], [])

    def test_validation_health_snapshot_reports_missing_matches_and_coverage_gaps(self) -> None:
        importer = self.CmDataImporter
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_run_status", "failed")
        self.env["integration.cm_data.pricing.audit"].create(
            {
                "issue_type": "missing_partner",
                "catalog_code": "stamford",
            }
        )

        with mock.patch(
            "odoo.addons.cm_data_import.models.cm_data_importer.CmDataClient",
            return_value=_CmDataClientStub(
                account_rows=[_account_row(record_id=101, account_name="Riverhead")],
                contact_rows=[_contact_row(record_id=501, account_name="Unknown Account")],
            ),
        ):
            snapshot = importer.get_validation_health_snapshot()
        checks = cast(dict[str, object], snapshot["checks"])
        metrics = cast(dict[str, object], snapshot["metrics"])
        samples = cast(dict[str, object], snapshot["samples"])

        self.assertFalse(snapshot["ok"])
        self.assertFalse(checks["last_run_success"])
        self.assertFalse(checks["contact_account_match_clean"])
        self.assertFalse(checks["contact_external_id_coverage_complete"])
        self.assertFalse(checks["pricing_missing_partner_clear"])
        self.assertEqual(metrics["missing_contact_external_id_count"], 1)
        self.assertEqual(metrics["pricing_missing_partner_count"], 1)
        self.assertEqual(samples["top_unmatched_account_names"], [["Unknown Account", 1]])
