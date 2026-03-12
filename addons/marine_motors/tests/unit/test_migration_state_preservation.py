import importlib.util
from pathlib import Path
from types import ModuleType

from ... import hooks
from ..common_imports import common
from ..fixtures.base import UnitTestCase


def _load_base_pre_migration_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[3] / "openupgrade_scripts_custom" / "scripts" / "base" / "19.0.1.0" / "pre-migration.py"
    spec = importlib.util.spec_from_file_location("openupgrade_base_pre_migration", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load migration module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@common.tagged(*common.UNIT_TAGS)
class TestMigrationStatePreservation(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config_parameter_model = self.env["ir.config_parameter"].sudo()
        self._clear_snapshot()

    def tearDown(self) -> None:
        self._clear_snapshot()
        super().tearDown()

    def _clear_snapshot(self) -> None:
        self.config_parameter_model.search([("key", "=", hooks.MARINE_MOTORS_SNAPSHOT_PARAMETER)]).unlink()

    def _xmlid_names(self, records: "odoo.models.BaseModel") -> list[str]:
        external_id_map = records.get_external_id()
        xmlid_names: list[str] = []
        for xmlid in external_id_map.values():
            xmlid_names.append(xmlid.split(".", 1)[1] if "." in xmlid else xmlid)
        return sorted(xmlid_names)

    def _recordset_from_xmlids(self, model_name: str, xmlids: list[str]) -> "odoo.models.BaseModel":
        model: "odoo.models.BaseModel" = self.env[model_name]
        record_ids: list[int] = []
        for xmlid in xmlids:
            record = self.env.ref(f"marine_motors.{xmlid}")
            record_ids.append(record.id)
        return model.browse(record_ids)

    def test_snapshot_and_restore_verified_marine_motors_split_state(self) -> None:
        migration_module = _load_base_pre_migration_module()

        trim_tilt_status = self.env.ref("marine_motors.motor_test_template_trim_tilt_unit_status")
        trim_unit = self.env.ref("marine_motors.motor_part_trim_unit")
        lower_unit = self.env.ref("marine_motors.motor_part_lower_unit")
        fuel_pump = self.env.ref("marine_motors.motor_part_fuel_pump")
        additional_section = self.env.ref("marine_motors.motor_test_section_additional")
        carburetors = self.env.ref("marine_motors.motor_part_carburetors")
        ecu = self.env.ref("marine_motors.motor_part_ecu")

        trim_tilt_selection_xmlids = [
            "option_manual",
            "option_needs_attention",
            "option_no_issues",
            "option_not_tested",
        ]
        lower_unit_hidden_test_xmlids = [
            "motor_test_template_drive_engages_forward",
            "motor_test_template_drive_engages_neutral",
            "motor_test_template_drive_engages_reverse",
            "motor_test_template_drive_shaft_seals_leaking",
            "motor_test_template_lower_unit_fluid_has_metal",
            "motor_test_template_lower_unit_fluid_has_water",
            "motor_test_template_lower_unit_gear_engages",
            "motor_test_template_lower_unit_holds_pressure",
            "motor_test_template_lower_unit_rotation_check",
            "motor_test_template_lower_unit_rotation_check_when_removed",
            "motor_test_template_prop_shaft_seals_leaking",
            "motor_test_template_shaft_length",
            "motor_test_template_shift_shaft_seals_leaking",
        ]

        trim_tilt_status.write(
            {
                "selection_options": [
                    (6, 0, self._recordset_from_xmlids("motor.test.selection", trim_tilt_selection_xmlids).ids)
                ]
            }
        )
        trim_unit.write(
            {
                "hidden_tests": [
                    (6, 0, self._recordset_from_xmlids("motor.test.template", ["motor_test_template_trim_tilt_unit_status"]).ids)
                ]
            }
        )
        lower_unit.write(
            {
                "hidden_tests": [
                    (6, 0, self._recordset_from_xmlids("motor.test.template", lower_unit_hidden_test_xmlids).ids)
                ]
            }
        )
        fuel_pump.write({"hidden_tests": [(6, 0, [])]})
        additional_section.write({"sequence": 8})
        carburetors.write({"name": "Carburetors/Injectors/ThrottleBody"})
        ecu.write({"name": "ECU/CDI"})
        self.env.flush_all()

        migration_module._snapshot_marine_motors_split_state(self.env)

        trim_tilt_status.write(
            {
                "selection_options": [
                    (6, 0, self._recordset_from_xmlids("motor.test.selection", trim_tilt_selection_xmlids + ["option_bad_motor"]).ids)
                ]
            }
        )
        trim_unit.write(
            {
                "hidden_tests": [
                    (
                        6,
                        0,
                        self._recordset_from_xmlids(
                            "motor.test.template",
                            ["motor_test_template_trim_tilt_unit_status", "motor_test_template_trim_tilt_unit_leaks"],
                        ).ids,
                    )
                ]
            }
        )
        lower_unit.write(
            {
                "hidden_tests": [
                    (
                        6,
                        0,
                        self._recordset_from_xmlids(
                            "motor.test.template",
                            lower_unit_hidden_test_xmlids[:10],
                        ).ids,
                    )
                ]
            }
        )
        fuel_pump.write(
            {
                "hidden_tests": [
                    (
                        6,
                        0,
                        self._recordset_from_xmlids(
                            "motor.test.template",
                            ["motor_test_template_fuel_pump_is_electric", "motor_test_template_fuel_pump_status"],
                        ).ids,
                    )
                ]
            }
        )
        additional_section.write({"sequence": 7})
        carburetors.write({"name": "Carburetors"})
        ecu.write({"name": "ECU"})

        hooks._restore_marine_motors_split_state(self.env)

        self.assertEqual(self._xmlid_names(trim_tilt_status.selection_options), trim_tilt_selection_xmlids)
        self.assertEqual(
            self._xmlid_names(trim_unit.hidden_tests),
            ["motor_test_template_trim_tilt_unit_status"],
        )
        self.assertEqual(self._xmlid_names(lower_unit.hidden_tests), lower_unit_hidden_test_xmlids)
        self.assertEqual(self._xmlid_names(fuel_pump.hidden_tests), [])
        self.assertEqual(additional_section.sequence, 8)
        self.assertEqual(carburetors.name, "Carburetors/Injectors/ThrottleBody")
        self.assertEqual(ecu.name, "ECU/CDI")
        self.assertFalse(self.config_parameter_model.search_count([("key", "=", hooks.MARINE_MOTORS_SNAPSHOT_PARAMETER)]))
