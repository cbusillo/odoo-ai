from .common_imports import TransactionCase, tagged, UNIT_TAGS, MODULE_TAG


@tagged(*UNIT_TAGS, MODULE_TAG)
class TestNameSettings(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]
        cls.Settings = cls.env["res.config.settings"]
        cls.ICP = cls.env["ir.config_parameter"].sudo()

    def test_settings_format_updates_icp_and_affects_name(self) -> None:
        emp = self.Employee.create({"first_name": "Wei", "last_name": "Zhang"})
        emp.invalidate_recordset(["name"])  # ensure compute ran
        self.assertEqual(emp.name, "Wei Zhang")

        settings = self.Settings.create({"user_name_format": "asian"})
        settings.execute()

        fmt = (self.ICP.get_param("user_name_extended.format") or "").strip()
        self.assertEqual(fmt, "asian")

        emp.invalidate_recordset(["name"])  # recompute under new format
        self.assertEqual(emp.name, "Zhang Wei")

    def test_settings_custom_pattern_applies(self) -> None:
        emp = self.Employee.create({"first_name": "Robert", "last_name": "Johnson", "nick_name": "Bob"})

        settings = self.Settings.create(
            {
                "user_name_format": "custom",
                "user_name_custom_pattern": "{last_name}, {first_name} ({nickname})",
            }
        )
        settings.execute()

        fmt = (self.ICP.get_param("user_name_extended.format") or "").strip()
        pat = (self.ICP.get_param("user_name_extended.custom_pattern") or "").strip()
        self.assertEqual(fmt, "custom")
        self.assertIn("{last_name}", pat)

        emp.invalidate_recordset(["name"])  # recompute with custom pattern
        self.assertEqual(emp.name, "Johnson, Robert (Bob)")
