from ...migrations.employee_external_identity import migrate_employee_identity_external_ids
from ...services.cm_data_client import CmDataEmployee
from ..common_imports import common
from ..fixtures.base import UnitTestCase

LEGACY_EMPLOYEE_IDENTITY_COLUMNS = (
    "cm_data_timeclock_id",
    "cm_data_repairshopr_id",
    "cm_data_discord_id",
)


@common.tagged(*common.UNIT_TAGS)
class TestEmployeeExternalIdentityMigration(UnitTestCase):
    def _add_legacy_identity_columns(self, column_definitions: dict[str, str]) -> None:
        for column_name, column_type in column_definitions.items():
            self.env.cr.execute(f"ALTER TABLE hr_employee ADD COLUMN IF NOT EXISTS {column_name} {column_type}")

    def _assert_legacy_identity_columns_removed(self) -> None:
        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = ANY(%s)
            """,
            ("hr_employee", list(LEGACY_EMPLOYEE_IDENTITY_COLUMNS)),
        )
        self.assertFalse(self.env.cr.fetchall())

    def _update_legacy_identity_columns(self, employee_id: int, column_values: dict[str, object]) -> None:
        assignments = ", ".join([f"{column_name} = %s" for column_name in column_values])
        parameters = [*column_values.values(), employee_id]
        self.env.cr.execute(
            f"UPDATE hr_employee SET {assignments} WHERE id = %s",
            parameters,
        )

    def test_migration_moves_employee_identity_columns_to_external_ids_and_drops_columns(self) -> None:
        employee = self.env["hr.employee"].create(
            {
                "name": "Migrated Employee",
                "first_name": "Migrated",
                "last_name": "Employee",
            }
        )

        self._add_legacy_identity_columns(
            {
                "cm_data_timeclock_id": "INTEGER",
                "cm_data_repairshopr_id": "INTEGER",
                "cm_data_discord_id": "VARCHAR",
            }
        )
        self._update_legacy_identity_columns(
            employee.id,
            {
                "cm_data_timeclock_id": 42,
                "cm_data_repairshopr_id": 314,
                "cm_data_discord_id": "271828182845904523",
            },
        )

        migrate_employee_identity_external_ids(self.env.cr)

        employee.invalidate_recordset()
        self.assertEqual(employee.search_by_external_id("timeclock", "42"), employee)
        self.assertEqual(employee.search_by_external_id("repairshopr", "314"), employee)
        self.assertEqual(employee.search_by_external_id("discord", "271828182845904523"), employee)
        self._assert_legacy_identity_columns_removed()

    def test_migration_raises_when_employee_identity_conflicts(self) -> None:
        first_employee = self.env["hr.employee"].create(
            {
                "name": "First Employee",
                "first_name": "First",
                "last_name": "Employee",
            }
        )
        second_employee = self.env["hr.employee"].create(
            {
                "name": "Second Employee",
                "first_name": "Second",
                "last_name": "Employee",
            }
        )
        first_employee.set_external_id("discord", "271828182845904523")

        self._add_legacy_identity_columns({"cm_data_discord_id": "VARCHAR"})
        self._update_legacy_identity_columns(
            second_employee.id,
            {"cm_data_discord_id": "271828182845904523"},
        )

        with self.assertRaises(RuntimeError):
            migrate_employee_identity_external_ids(self.env.cr)

    def test_sync_employee_external_ids_raises_when_binding_conflicts(self) -> None:
        conflicting_employee = self.env["hr.employee"].create(
            {
                "name": "Conflicting Employee",
                "first_name": "Conflicting",
                "last_name": "Employee",
            }
        )
        imported_employee = self.env["hr.employee"].create(
            {
                "name": "Imported Employee",
                "first_name": "Imported",
                "last_name": "Employee",
            }
        )
        conflicting_employee.set_external_id("discord", "271828182845904523")

        employee_row = CmDataEmployee(
            record_id=501,
            legal_name="Imported Employee",
            legal_last="Employee",
            legal_first="Imported",
            name="Imported Employee",
            repairshopr_id=None,
            timeclock_id=None,
            discord_id=271828182845904523,
            grafana_username=None,
            date_of_hire=None,
            date_of_birth=None,
            last_day=None,
            dept=None,
            team=None,
            active=True,
            on_site=True,
        )

        with self.assertRaises(RuntimeError):
            self.CmDataImporter._sync_employee_external_ids(imported_employee, employee_row)

    def test_sync_employee_external_ids_reactivates_archived_systems(self) -> None:
        imported_employee = self.env["hr.employee"].create(
            {
                "name": "Archived System Employee",
                "first_name": "Archived",
                "last_name": "System",
            }
        )
        discord_system = self.env["external.system"].ensure_system(
            code="discord",
            name="Discord",
            id_format=r"^\d{17,20}$",
            sequence=30,
            url="https://discord.com",
            applicable_model_xml_ids=("hr.model_hr_employee",),
        )
        discord_system.active = False

        employee_row = CmDataEmployee(
            record_id=777,
            legal_name="Archived System Employee",
            legal_last="System",
            legal_first="Archived",
            name="Archived System Employee",
            repairshopr_id=None,
            timeclock_id=None,
            discord_id=271828182845904523,
            grafana_username=None,
            date_of_hire=None,
            date_of_birth=None,
            last_day=None,
            dept=None,
            team=None,
            active=True,
            on_site=True,
        )

        self.CmDataImporter._sync_employee_external_ids(imported_employee, employee_row)

        discord_system.invalidate_recordset()
        self.assertTrue(discord_system.active)
        self.assertEqual(imported_employee.search_by_external_id("discord", "271828182845904523"), imported_employee)

    def test_sync_employee_external_ids_reclaims_archived_same_model_mapping(self) -> None:
        archived_employee = self.env["hr.employee"].create(
            {
                "name": "Archived Mapping Employee",
                "first_name": "Archived",
                "last_name": "Mapping",
            }
        )
        imported_employee = self.env["hr.employee"].create(
            {
                "name": "Reclaiming Employee",
                "first_name": "Reclaiming",
                "last_name": "Employee",
            }
        )
        archived_employee.set_external_id("discord", "271828182845904523")
        archived_employee.get_external_id_record("discord", "default", active_only=False).active = False

        employee_row = CmDataEmployee(
            record_id=778,
            legal_name="Reclaiming Employee",
            legal_last="Employee",
            legal_first="Reclaiming",
            name="Reclaiming Employee",
            repairshopr_id=None,
            timeclock_id=None,
            discord_id=271828182845904523,
            grafana_username=None,
            date_of_hire=None,
            date_of_birth=None,
            last_day=None,
            dept=None,
            team=None,
            active=True,
            on_site=True,
        )

        self.CmDataImporter._sync_employee_external_ids(imported_employee, employee_row)

        self.assertEqual(imported_employee.search_by_external_id("discord", "271828182845904523"), imported_employee)
