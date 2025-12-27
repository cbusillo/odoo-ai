from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from .common_imports import tagged, UNIT_TAGS, MODULE_TAG


@tagged(*UNIT_TAGS, MODULE_TAG)
class TestEmployeeName(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]
        cls.ICP = cls.env["ir.config_parameter"].sudo()

    def test_create_and_defaults(self) -> None:
        emp = self.Employee.create({"first_name": "John", "last_name": "Doe"})
        self.assertEqual(emp.nick_name, "John")
        self.assertEqual(emp.name, "John Doe")
        self.assertEqual(emp.display_name, "John Doe")

    def test_display_with_nickname(self) -> None:
        emp = self.Employee.create({"first_name": "William", "last_name": "Gates", "nick_name": "Bill"})
        self.assertEqual(emp.display_name, "Bill (William Gates)")

    def test_validation_spaces(self) -> None:
        with self.assertRaises(ValidationError):
            self.Employee.create({"first_name": "  John  ", "last_name": "Doe"})

    def test_name_search(self) -> None:
        emp = self.Employee.create({"first_name": "Alice", "last_name": "Smith", "nick_name": "Ally"})
        ids = [rid for rid, _ in self.Employee.name_search("Ally")]
        self.assertIn(emp.id, ids)

    def test_inverse_on_name_write(self) -> None:
        self.ICP.set_param("user_name_extended.format", "asian")
        emp = self.Employee.create({"first_name": "Wei", "last_name": "Zhang"})
        emp.name = "Li Wei"
        emp.invalidate_recordset(["first_name", "last_name", "name"])
        self.assertEqual(emp.first_name, "Wei")
        self.assertEqual(emp.last_name, "Li")
        self.assertEqual(emp.name, "Li Wei")

    def test_external_partner_user_changes_do_not_break(self) -> None:
        partner = self.env["res.partner"].create({"name": "Partner A"})
        user = self.env["res.users"].create({"name": "User A", "login": "u@example.com", "partner_id": partner.id})
        emp = self.Employee.create({"first_name": "Jane", "last_name": "Doe", "user_id": user.id, "work_contact_id": partner.id})
        partner.name = "Changed Partner"
        user.name = "Changed User"
        emp.invalidate_recordset(["first_name", "last_name", "name"])
        self.assertEqual(emp.first_name, "Jane")
        self.assertEqual(emp.last_name, "Doe")

    def test_opt_in_sync_via_context(self) -> None:
        partner = self.env["res.partner"].create({"name": "Partner B"})
        emp = self.Employee.create({"first_name": "Carl", "last_name": "Sagan", "work_contact_id": partner.id})
        partner.with_context(allow_employee_sync=True).write({"name": "Sagan Carl"})
        emp.invalidate_recordset(["first_name", "last_name", "name"])
        self.ICP.set_param("user_name_extended.format", "asian")
        partner.with_context(allow_employee_sync=True).write({"name": "Sagan Carl"})
        emp.invalidate_recordset(["first_name", "last_name", "name"])
        self.assertEqual(emp.first_name, "Carl")
        self.assertEqual(emp.last_name, "Sagan")
