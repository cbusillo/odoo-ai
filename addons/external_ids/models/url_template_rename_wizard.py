from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ExternalSystemUrlRenameWizard(models.TransientModel):
    _name = "external.system.url.rename.wizard"
    _description = "Rename External System URL Code"

    url_id = fields.Many2one("external.system.url", required=True)
    new_code = fields.Char(required=True)

    @api.model
    def default_get(self, fields_list: list[str]) -> dict[str, str | int | bool]:
        res = super().default_get(fields_list)
        url = self.env["external.system.url"].browse(self.env.context.get("default_url_id"))
        if url:
            res.setdefault("new_code", url.code)
        return res

    def action_rename(self) -> dict:
        self.ensure_one()
        url = self.url_id
        if not url:
            raise ValidationError("No URL template selected")
        sanitized = url._sanitize_code(self.new_code)
        if not sanitized:
            raise ValidationError("Code cannot be empty")
        # Write; SQL constraint will guard uniqueness
        url.with_context(allow_url_code_write=True).write({"code": sanitized})
        return {"type": "ir.actions.act_window_close"}
