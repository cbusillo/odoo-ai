from odoo import models
from ..tools.name import NameFormatter


class HrNameSyncMixin(models.AbstractModel):
    _name = "hr.name.sync.mixin"
    _description = "Name sync helpers"

    def _sync_name_to_employees_common(self, new_name: str, employee_domain: list) -> None:
        if not new_name:
            return
        employees = self.env["hr.employee"].search(employee_domain)
        if not employees:
            return
        icp = self.env["ir.config_parameter"].sudo()
        fmt = (icp.get_param("user_name_extended.format") or "western").strip().lower()
        parsed = NameFormatter.split_full_name(new_name, fmt)
        first = (parsed.get("first_name") or "").strip()
        if not first:
            return
        vals = {"first_name": first}
        last = (parsed.get("last_name") or "").strip()
        if last:
            vals["last_name"] = last
        employees.with_context(skip_name_propagation=True).write(vals)
