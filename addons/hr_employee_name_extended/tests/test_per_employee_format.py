from odoo.tests import TransactionCase
from .common_imports import tagged, UNIT_TAGS, MODULE_TAG


@tagged(*UNIT_TAGS, MODULE_TAG)
class TestPerEmployeeFormat(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]
        cls.ICP = cls.env["ir.config_parameter"].sudo()

    def test_default_from_settings_and_override(self) -> None:
        self.ICP.set_param("user_name_extended.format", "western")

        emp_default = self.Employee.create({"first_name": "Li", "last_name": "Wei"})
        emp_default.invalidate_recordset(["name"])  # ensure compute
        self.assertEqual(emp_default.name, "Li Wei")
        self.assertIn(emp_default.name_format, ("", "western"))

        emp_asian = self.Employee.create({"first_name": "Wei", "last_name": "Zhang", "name_format": "asian"})
        emp_asian.invalidate_recordset(["name"])  # ensure compute
        self.assertEqual(emp_asian.name, "Zhang Wei")

    def test_inverse_respects_employee_format(self) -> None:
        self.ICP.set_param("user_name_extended.format", "western")

        emp = self.Employee.create({"first_name": "Wei", "last_name": "Zhang", "name_format": "asian"})
        emp.name = "Li Wei"
        emp.invalidate_recordset(["first_name", "last_name", "name"])  # recompute and fetch
        self.assertEqual(emp.first_name, "Wei")
        self.assertEqual(emp.last_name, "Li")

    def test_default_get_uses_icp(self) -> None:
        self.ICP.set_param("user_name_extended.format", "asian")
        vals = self.Employee.default_get(["name_format"])  # type: ignore[call-arg]
        self.assertEqual(vals.get("name_format"), "asian")

        self.ICP.set_param("user_name_extended.format", "custom")
        vals2 = self.Employee.default_get(["name_format"])  # type: ignore[call-arg]
        self.assertIn(vals2.get("name_format"), ("", None))

        self.ICP.set_param("user_name_extended.format", "")
        vals3 = self.Employee.default_get(["name_format"])  # type: ignore[call-arg]
        self.assertIn(vals3.get("name_format"), ("", None))
