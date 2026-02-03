from typing import Any
from odoo import models, api, fields
from lxml import etree


class View(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(
        selection_add=[("multigraph", "MultiGraph")],
        ondelete={"multigraph": "cascade"},
    )

    @api.model
    def _postprocess_view(self, node: etree.ElementBase, model: str | None = None, **options: dict[str, Any]) -> etree.ElementBase:
        if node.tag == "multigraph":
            node = self._postprocess_multigraph_view(node, model)
        return super()._postprocess_view(node, model, **options)

    def _postprocess_multigraph_view(self, node: etree.ElementBase, model_name: str | None = None) -> etree.ElementBase:
        if model_name is None:
            return node

        model = self.env[model_name]

        for field_node in node.xpath('.//field[@type="measure"]'):
            field_name = field_node.get("name")
            if field_name and field_name in model._fields:
                field = model._fields[field_name]

                if not field_node.get("string"):
                    field_node.set("string", field.string or field_name)

                if field_node.get("widget") == "monetary" and not field_node.get("options"):
                    field_node.set("options", '{"currency_field": "currency_id"}')

                if not field_node.get("axis"):
                    field_node.set("axis", "y")

        return node

    @api.model
    def _get_view_info(self) -> dict[str, dict[str, str | bool]]:
        result = super()._get_view_info()
        result["multigraph"] = {
            "icon": "fa fa-line-chart",
            "multi_record": True,
        }
        return result
