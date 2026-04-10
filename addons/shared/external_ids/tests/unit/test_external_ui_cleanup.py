from ...migrations.external_ui_cleanup import (
    deactivate_obsolete_external_id_views,
    unlink_obsolete_external_id_views,
)
from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestExternalIdUiCleanup(UnitTestCase):
    def _create_obsolete_view(self, xmlid_name: str, *, active: bool = True) -> "odoo.model.ir_ui_view":
        view = self.env["ir.ui.view"].create(
            {
                "name": f"obsolete.{xmlid_name}",
                "type": "form",
                "model": "res.partner",
                "inherit_id": self.env.ref("base.view_partner_form").id,
                "arch": "<xpath expr=\"//sheet\" position=\"inside\"><group/></xpath>",
                "active": active,
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "external_ids",
                "name": xmlid_name,
                "model": "ir.ui.view",
                "res_id": view.id,
            }
        )
        return view

    def test_deactivate_obsolete_external_id_views_marks_known_views_inactive(self) -> None:
        obsolete_view = self._create_obsolete_view("view_product_template_form_external_ids")

        view_ids = deactivate_obsolete_external_id_views(self.env.cr)

        obsolete_view.invalidate_recordset(["active"])
        self.assertIn(obsolete_view.id, view_ids)
        self.assertFalse(obsolete_view.active)

    def test_unlink_obsolete_external_id_views_removes_views_and_xmlids(self) -> None:
        partner_view = self._create_obsolete_view("view_partner_form_external_ids")
        employee_view = self._create_obsolete_view("view_employee_form_external_ids")

        removed_view_ids = unlink_obsolete_external_id_views(self.env.cr)

        self.assertIn(partner_view.id, removed_view_ids)
        self.assertIn(employee_view.id, removed_view_ids)
        self.assertFalse(partner_view.exists())
        self.assertFalse(employee_view.exists())
        self.assertFalse(
            self.env["ir.model.data"].search_count(
                [
                    ("module", "=", "external_ids"),
                    ("name", "in", ["view_partner_form_external_ids", "view_employee_form_external_ids"]),
                ]
            )
        )
