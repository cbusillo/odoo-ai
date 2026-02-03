from lxml import etree

from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestViewsLoad(UnitTestCase):
    def _fields_in_form(self, model_name: str, view_xmlid: str) -> list[str]:
        view = self.env.ref(view_xmlid)
        model = self.env[model_name]
        if hasattr(model, "fields_view_get"):
            info = model.fields_view_get(view_id=view.id, view_type="form")
        else:
            info = model.get_view(view_id=view.id, view_type="form")
        arch_source = info.get("arch") or info.get("arch_base") or ""
        arch = etree.fromstring(arch_source.encode())
        fields = {node.get("name") for node in arch.xpath(".//field[@name]")}
        return [field_name for field_name in fields if field_name in model._fields]

    def _assert_form_read_ok(self, model_name: str, create_vals: dict, view_xmlid: str) -> None:
        fields = self._fields_in_form(model_name, view_xmlid)
        rec = self.env[model_name].create(create_vals)
        data = rec.read(fields)
        self.assertTrue(isinstance(data, list) and data, f"No data returned for {model_name}")

    def test_product_template_form_reads(self) -> None:
        self._assert_form_read_ok(
            "product.template",
            {"name": "View Test Product"},
            "external_ids.view_product_template_form_external_ids",
        )

    def test_partner_form_reads(self) -> None:
        self._assert_form_read_ok(
            "res.partner",
            {"name": "View Test Partner"},
            "external_ids.view_partner_form_external_ids",
        )

    def test_employee_form_reads(self) -> None:
        employee_model = self.env["hr.employee"]
        employee_values = {"name": "View Test Employee"}
        if "first_name" in employee_model._fields:
            employee_values["first_name"] = "View"
        if "last_name" in employee_model._fields:
            employee_values["last_name"] = "Employee"
        self._assert_form_read_ok(
            "hr.employee",
            employee_values,
            "external_ids.view_employee_form_external_ids",
        )

    def test_external_system_form_reads(self) -> None:
        self._assert_form_read_ok(
            "external.system",
            {"name": "View Test System", "code": "view_test"},
            "external_ids.view_external_system_form",
        )

    def test_external_id_form_reads(self) -> None:
        system = self.env["external.system"].create({"name": "Sys", "code": "sys"})
        partner = self.env["res.partner"].create({"name": "Partner X"})
        ext = self.env["external.id"].create(
            {
                "system_id": system.id,
                "external_id": "ABC123",
                "res_model": "res.partner",
                "res_id": partner.id,
            }
        )
        fields = self._fields_in_form("external.id", "external_ids.view_external_id_form")
        data = ext.read(fields)
        self.assertTrue(data)

    def test_actions_exist(self) -> None:
        self.env.ref("external_ids.action_external_id")
        self.env.ref("external_ids.action_external_system")
        self.env.ref("external_ids.action_external_system_url")
