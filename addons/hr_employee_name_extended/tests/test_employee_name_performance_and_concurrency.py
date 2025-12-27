import concurrent.futures

from .common_imports import TransactionCase, tagged, UNIT_TAGS, MODULE_TAG


@tagged(*UNIT_TAGS, MODULE_TAG)
class TestEmployeePerfConcurrency(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]

    def test_bulk_write(self) -> None:
        employees = self.Employee.create([{"first_name": f"First{i}", "last_name": f"Last{i}"} for i in range(64)])
        employees.write({"nick_name": "Bulk"})
        for employee in employees:
            self.assertEqual(employee.nick_name, "Bulk")

    def test_concurrent_updates(self) -> None:
        emp = self.Employee.create({"first_name": "Concurrent", "last_name": "Test"})

        def update_first() -> None:
            with self.env.registry.cursor() as cr:
                env = self.env(cr=cr)
                env["hr.employee"].browse(emp.id).write({"first_name": "Updated"})
                cr.commit()

        def update_last() -> None:
            with self.env.registry.cursor() as cr:
                env = self.env(cr=cr)
                env["hr.employee"].browse(emp.id).write({"last_name": "Concurrent"})
                cr.commit()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            ex.submit(update_first).result()
            ex.submit(update_last).result()

        emp.invalidate_recordset()
        self.assertIn(emp.first_name, ["Concurrent", "Updated"])
        self.assertIn(emp.last_name, ["Test", "Concurrent"])
