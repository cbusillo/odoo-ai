from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from ..tools.name import NameFormatter


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = "hr.employee"

    first_name = fields.Char(index=True, tracking=True)
    last_name = fields.Char(index=True, tracking=True)
    nick_name = fields.Char(index=True, tracking=True)

    name_format = fields.Selection(
        selection=[
            ("", "System Default"),
            ("western", "Western: First Last"),
            ("asian", "Asian: Last First"),
        ],
        default="",
        help="Optional per-employee override for name order.",
    )

    name = fields.Char(
        compute="_compute_name",
        inverse="_inverse_name",
        store=True,
        readonly=False,
        index=True,
    )

    # Use name_get instead of storing a custom display name

    @api.model_create_multi
    def create(self, vals_list: "list[odoo.values.hr_employee]") -> "odoo.model.hr_employee":
        for vals in vals_list:
            first = (vals.get("first_name") or "").strip()
            last = (vals.get("last_name") or "").strip()
            if not first and not last:
                raise ValidationError(_("At least one of First Name or Last Name is required."))
            if not vals.get("nick_name"):
                vals["nick_name"] = first or last
        recs = super().create(vals_list)
        return recs

    @api.model
    def default_get(self, fields_list: list[str]) -> dict[str, str | int | bool]:
        values = super().default_get(fields_list)
        if "name_format" in fields_list:
            icp = self.env["ir.config_parameter"].sudo()
            fmt = (icp.get_param("user_name_extended.format") or "").strip().lower()
            values["name_format"] = fmt if fmt in {"western", "asian"} else ""
        return values

    def write(self, vals: "odoo.values.hr_employee") -> bool:
        if "nick_name" in vals and not (vals["nick_name"] or "").strip() and "first_name" not in vals:
            vals = dict(vals)
            vals["nick_name"] = self.first_name
        return super().write(vals)

    @api.depends("first_name", "last_name", "name_format")
    def _compute_name(self) -> None:
        for rec in self:
            rec.name = NameFormatter.compose_legal_name(rec.env, rec.first_name or "", rec.last_name or "", rec.name_format or None)

    def _inverse_name(self) -> None:
        for rec in self:
            if not rec.name:
                continue
            icp = rec.env["ir.config_parameter"].sudo()
            eff_fmt = (rec.name_format or (icp.get_param("user_name_extended.format") or "western")).strip().lower()
            parsed = NameFormatter.split_full_name(rec.name, eff_fmt)
            vals = {}
            fn = parsed.get("first_name", "").strip()
            ln = parsed.get("last_name", "").strip()
            if fn and fn != (rec.first_name or ""):
                vals["first_name"] = fn
            if ln and ln != (rec.last_name or ""):
                vals["last_name"] = ln
            if vals:
                rec.with_context(skip_name_propagation=True).write(vals)

    def name_get(self):  # type: ignore[override]
        res = []
        for rec in self:
            nick = (rec.nick_name or "").strip()
            first = (rec.first_name or "").strip()
            if nick and nick != first:
                base = rec.name or NameFormatter.compose_legal_name(
                    rec.env, rec.first_name or "", rec.last_name or "", rec.name_format or None
                )
                name = f"{nick} ({base})"
            else:
                name = rec.name or ""
            res.append((rec.id, name))
        return res

    @api.constrains("first_name", "last_name", "nick_name")
    def _check_name_parts(self) -> None:
        for rec in self:
            for fname in ("first_name", "last_name", "nick_name"):
                val = getattr(rec, fname)
                if val and val != val.strip():
                    raise ValidationError(_("%s should not contain leading or trailing spaces.") % rec._fields[fname].string)

    @api.model
    def name_search(
        self, name: str = "", args: list | None = None, operator: str = "ilike", limit: int = 100
    ) -> list[tuple[int, str]]:
        args = list(args or [])
        if name:
            fields_to_search = ("name", "first_name", "last_name", "nick_name")
            or_domain = [(f, operator, name) for f in fields_to_search]
            args = fields.Domain.AND([args, fields.Domain.OR([[condition] for condition in or_domain])])
        recs = self.search(args, limit=limit)
        return [(rec.id, rec.display_name or rec.name) for rec in recs]

    @api.model
    def _action_recompute_names(self) -> None:
        last_id = 0
        limit = 500
        while True:
            batch = self.search([("id", ">", last_id)], order="id", limit=limit)
            if not batch:
                break
            # Invalidate and force recompute of stored name
            batch.invalidate_recordset(["name"])  # type: ignore[arg-type]
            # Force compute by reading
            batch.mapped("name")
            last_id = batch[-1].id
