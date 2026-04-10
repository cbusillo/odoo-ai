from datetime import datetime

from ...models.cm_data_importer import (
    EMPLOYEE_TIMECLOCK_PLACEHOLDER_RESOURCE,
    EXTERNAL_SYSTEM_CODE,
    CmDataTimeclockPunch,
)
from ...services.cm_data_client import CmDataEmployee
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _employee_row(*, record_id: int, timeclock_id: int | None) -> CmDataEmployee:
    return CmDataEmployee(
        record_id=record_id,
        legal_name=f"Employee {record_id}",
        legal_last=None,
        legal_first=None,
        name=f"Employee {record_id}",
        repairshopr_id=None,
        timeclock_id=timeclock_id,
        discord_id=None,
        grafana_username=None,
        date_of_hire=None,
        date_of_birth=None,
        last_day=None,
        dept=None,
        team=None,
        active=True,
        on_site=True,
    )


def _punch_row(*, record_id: int, user_id: int | None, compnum: int | None) -> CmDataTimeclockPunch:
    return CmDataTimeclockPunch(
        record_id=record_id,
        compnum=compnum,
        user_id=user_id,
        check_type=None,
        check_time=datetime(2026, 3, 14, 9),
        sensor_id=None,
        checked=None,
        reason=None,
        work_type=None,
        check_number=None,
        created_by=None,
        edited_by=None,
        created_date=None,
        edited_day=None,
        locked=False,
        time_received=None,
        exception=None,
        dept_code=None,
        comment=None,
    )


@common.tagged(*common.UNIT_TAGS)
class TestTimeclockEmployeeMapping(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.CmDataImporter

    def test_build_timeclock_employee_map_includes_record_id_aliases(self) -> None:
        alias_map = self.importer._build_timeclock_employee_map(
            [
                _employee_row(record_id=10, timeclock_id=1038),
                _employee_row(record_id=17, timeclock_id=1039),
            ],
            {
                10: 110,
                17: 117,
            },
        )

        self.assertEqual(alias_map[1038], 110)
        self.assertEqual(alias_map[1039], 117)
        self.assertEqual(alias_map[10], 110)
        self.assertEqual(alias_map[17], 117)

    def test_build_timeclock_employee_map_keeps_timeclock_alias_precedence(self) -> None:
        alias_map = self.importer._build_timeclock_employee_map(
            [
                _employee_row(record_id=10, timeclock_id=1038),
                _employee_row(record_id=1038, timeclock_id=None),
            ],
            {
                10: 110,
                1038: 999,
            },
        )

        self.assertEqual(alias_map[1038], 110)
        self.assertEqual(alias_map[10], 110)

    def test_resolve_timeclock_employee_id_uses_record_id_fallback(self) -> None:
        employee_id = self.importer._resolve_timeclock_employee_id(
            _punch_row(record_id=1, user_id=39, compnum=1038),
            {
                39: 110,
                1038: 210,
            },
        )

        self.assertEqual(employee_id, 110)

    def test_resolve_timeclock_employee_id_uses_compnum_fallback(self) -> None:
        employee_id = self.importer._resolve_timeclock_employee_id(
            _punch_row(record_id=2, user_id=39, compnum=1038),
            {
                1038: 210,
            },
        )

        self.assertEqual(employee_id, 210)

    def test_collect_timeclock_placeholder_specs_groups_unresolved_compnums(self) -> None:
        placeholder_specs = self.importer._collect_timeclock_placeholder_specs(
            [
                _punch_row(record_id=1, user_id=50, compnum=42),
                CmDataTimeclockPunch(**{**_punch_row(record_id=2, user_id=50, compnum=42).__dict__, "check_time": datetime(
                    2026, 3, 15, 9)}),
                _punch_row(record_id=3, user_id=1038, compnum=1038),
            ],
            {
                1038: 210,
            },
        )

        self.assertEqual(set(placeholder_specs), {42})
        self.assertEqual(placeholder_specs[42]["first_seen"], datetime(2026, 3, 14, 9))
        self.assertEqual(placeholder_specs[42]["last_seen"], datetime(2026, 3, 15, 9))

    def test_ensure_timeclock_placeholder_employees_registers_compnum_alias(self) -> None:
        system = self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="CM Data",
            applicable_model_xml_ids=(),
        )
        sync_started_at = datetime(2026, 3, 14, 12)
        timeclock_employee_map: dict[int, int] = {}

        self.importer._ensure_timeclock_placeholder_employees(
            [
                _punch_row(record_id=1, user_id=50, compnum=42),
                _punch_row(record_id=2, user_id=50, compnum=42),
            ],
            timeclock_employee_map,
            system,
            sync_started_at,
        )

        placeholder_employee = self.env["hr.employee"].search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            "42",
            EMPLOYEE_TIMECLOCK_PLACEHOLDER_RESOURCE,
        )
        self.assertTrue(placeholder_employee)
        self.assertFalse(placeholder_employee.active)
        self.assertEqual(placeholder_employee.name, "Archived CM Employee 42")
        self.assertEqual(timeclock_employee_map[42], placeholder_employee.id)
