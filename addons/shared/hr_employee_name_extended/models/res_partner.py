from odoo import models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "hr.name.sync.mixin"]
    _description = "Partner"

    def write(self, vals: "odoo.values.res_partner") -> bool:
        res = super().write(vals)
        if "name" in vals and self.env.context.get("allow_employee_sync") and not self.env.context.get("skip_employee_sync"):
            self._sync_name_to_employees(vals["name"])
        return res

    def _sync_name_to_employees(self, new_name: str) -> None:
        domain = [("work_contact_id", "in", self.ids)]
        self._sync_name_to_employees_common(new_name, domain)
