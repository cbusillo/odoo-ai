from typing import Any

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ExternalId(models.Model):
    _name = "external.id"
    _description = "External System IDs"
    _order = "system_id, id"
    _rec_name = "display_name"

    res_model = fields.Char(string="Model", required=True, index=True, help="The model this external ID belongs to")
    res_id = fields.Integer(string="Record ID", required=True, index=True, help="The ID of the record in the model")
    resource = fields.Char(
        string="Resource",
        required=True,
        default="default",
        help="Dimension for multiple IDs per system per record (e.g., product, variant, customer, address)",
        index=True,
    )
    reference = fields.Reference(
        selection="_reference_models",
        compute="_compute_reference",
        inverse="_inverse_reference",
        search="_search_reference",
    )

    system_id = fields.Many2one(
        "external.system",
        string="External System",
        required=True,
        ondelete="restrict",
        domain="[('active','=',True), '|', ('applicable_model_ids','=',False), ('applicable_model_ids.model','=', (context.get('default_res_model') or res_model))]",
    )
    external_id = fields.Char(
        string="External ID",
        required=True,
        index=True,
        help="The ID of this record in the external system",
    )
    display_name = fields.Char(compute="_compute_display_name")
    record_name = fields.Char(compute="_compute_record_name")

    notes = fields.Text(help="Additional notes about this external ID")
    active = fields.Boolean(default=True, help="If unchecked, this external ID is considered inactive")
    last_sync = fields.Datetime(help="Last time this ID was synchronized with the external system")

    company_id = fields.Many2one(
        "res.company",
        compute="_compute_company_id",
        store=True,
        index=True,
        help="Company of the referenced record, if any.",
    )

    _unique_record_per_system_resource = models.Constraint(
        "unique(res_model, res_id, system_id, resource)",
        "Each record can have only one ID per external system and resource!",
    )
    _unique_external_id_per_system_resource = models.Constraint(
        "unique(system_id, resource, external_id)",
        "This external ID already exists for this system and resource!",
    )

    @api.model
    def default_get(self, fields_list: list[str]) -> dict[str, Any]:
        values = super().default_get(fields_list)
        ctx = self.env.context or {}
        # Robust defaults for inline one2many creation from parent forms
        res_model = ctx.get("default_res_model") or ctx.get("active_model")
        if "res_model" in fields_list and not values.get("res_model") and res_model:
            values["res_model"] = res_model
        if "resource" in fields_list and not values.get("resource"):
            values["resource"] = "default"
        # If coming from a specific record context, set reference hint (optional)
        if "reference" in fields_list and not values.get("reference") and res_model and ctx.get("default_res_id"):
            values["reference"] = f"{res_model},{ctx['default_res_id']}"
        return values

    @api.model_create_multi
    def create(self, vals_list: "list[odoo.values.external_id]") -> "odoo.model.external_id":
        # Ensure required res_model is populated even if view context omitted it
        ctx_res_model = (self.env.context or {}).get("default_res_model") or (self.env.context or {}).get("active_model")
        for vals in vals_list:
            if not vals.get("res_model") and ctx_res_model:
                vals["res_model"] = ctx_res_model
            if not vals.get("res_id") and (self.env.context or {}).get("default_res_id"):
                vals["res_id"] = (self.env.context or {}).get("default_res_id")
            if not vals.get("resource"):
                vals["resource"] = "default"
            if "external_id" in vals and isinstance(vals["external_id"], str):
                vals["external_id"] = vals["external_id"].strip()
        return super().create(vals_list)

    def write(self, vals: "odoo.values.external_id") -> bool:
        if "external_id" in vals and isinstance(vals["external_id"], str):
            vals = dict(vals)
            vals["external_id"] = vals["external_id"].strip()
        return super().write(vals)

    @api.model
    def _reference_models(self) -> list[tuple[str, str]]:
        # If a default target model is provided in context (opened from a parent),
        # restrict the selection to that model to avoid cross-model confusion.
        ctx = self.env.context or {}
        default_model = ctx.get("default_res_model")
        if default_model:
            try:
                label = self.env[default_model]._description or default_model
            except Exception:  # pragma: no cover
                label = default_model
            return [(default_model, label)]

        # Otherwise, detect eligible models by the presence of the mixin action.
        items: list[tuple[str, str]] = []
        for model_name in self.env:
            try:
                model = self.env[model_name]
            except Exception:  # pragma: no cover - defensive registry guard
                continue
            if getattr(model, "_abstract", False) or getattr(model, "_transient", False):
                continue
            if hasattr(model, "action_view_external_ids"):
                label = model._description or model_name
                items.append((model_name, label))
        items.sort(key=lambda x: x[1].lower())
        return items

    @api.depends("res_model", "res_id")
    def _compute_reference(self) -> None:
        for record in self:
            if record.res_model and record.res_id:
                record.reference = f"{record.res_model},{record.res_id}"
            else:
                record.reference = False

    def _inverse_reference(self) -> None:
        for record in self:
            if record.reference:
                ref_val = record.reference
                # The reference widget may provide a string like "model,id"
                # or a browsable recordset depending on context.
                if isinstance(ref_val, str):
                    model_name, _, rec_id = ref_val.partition(",")
                    record.res_model = model_name or False
                    try:
                        record.res_id = int(rec_id) if rec_id else False
                    except ValueError:
                        record.res_id = False
                else:
                    record.res_model = getattr(ref_val, "_name", False)
                    record.res_id = getattr(ref_val, "id", False)
            else:
                record.res_model = False
                record.res_id = False

    @staticmethod
    def _search_reference(
        operator: str,
        value: "odoo.model.res_partner | odoo.model.hr_employee | odoo.model.product_product | None",
    ) -> list[tuple[str, str, str | int]]:
        if operator == "=" and value:
            return [("res_model", "=", value._name), ("res_id", "=", value.id)]
        return []

    @api.depends("res_model", "res_id")
    def _compute_record_name(self) -> None:
        for record in self:
            if record.res_model and record.res_id:
                try:
                    referenced_record = self.env[record.res_model].browse(record.res_id)
                    if referenced_record.exists():
                        record.record_name = referenced_record.display_name
                    else:
                        record.record_name = f"[Deleted {record.res_model}]"
                except (KeyError, AttributeError, ValueError):
                    record.record_name = f"[Invalid {record.res_model}]"
            else:
                record.record_name = ""

    @api.depends("res_model", "res_id")
    def _compute_company_id(self) -> None:
        for record in self:
            company = False
            if record.res_model and record.res_id:
                try:
                    model = self.env[record.res_model]
                except KeyError:
                    model = None
                if model and "company_id" in model._fields:
                    ref = model.browse(record.res_id)
                    company = ref.company_id.id if ref.exists() else False
            record.company_id = company

    @api.depends("system_id.name", "system_id.id_prefix", "external_id", "record_name")
    def _compute_display_name(self) -> None:
        for record in self:
            if record.system_id and record.external_id:
                prefix = record.system_id.id_prefix or ""
                record_info = f" ({record.record_name})" if record.record_name else ""
                record.display_name = f"{record.system_id.name}: {prefix}{record.external_id}{record_info}"
            else:
                record.display_name = record.external_id or ""

    @api.constrains("external_id", "system_id")
    def _check_id_format(self) -> None:
        for record in self:
            if record.system_id.id_format:
                import re

                if not re.match(record.system_id.id_format, record.external_id):
                    raise ValidationError(
                        f"External ID '{record.external_id}' does not match the expected format "
                        f"for {record.system_id.name}: {record.system_id.id_format}"
                    )

    def action_sync(self) -> "odoo.values.ir_actions_client":
        self.ensure_one()
        self.last_sync = fields.Datetime.now()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sync Complete",
                "message": f"Synchronized {self.display_name}",
                "type": "success",
            },
        }

    @api.model
    def get_record_by_external_id(
        self, system_code: str, external_id: str
    ) -> "odoo.model.res_partner | odoo.model.hr_employee | odoo.model.product_product | None":
        System = self.env["external.system"]
        system = System.search([("code", "=", system_code)], limit=1)

        if not system:
            return None

        external_record = self.search(
            [("system_id", "=", system.id), ("external_id", "=", external_id), ("active", "=", True)], limit=1
        )

        if external_record and external_record.res_model and external_record.res_id:
            try:
                record = self.env[external_record.res_model].browse(external_record.res_id)
                if record.exists():
                    return record
            except (KeyError, AttributeError, ValueError):
                pass

        return None

    def name_search(
        self, name: str = "", args: list | None = None, operator: str = "ilike", limit: int = 80
    ) -> list[tuple[int, str]]:
        base = list(args or [])
        if not name:
            records = self.search(base, limit=limit)
            return [(record.id, record.display_name or "") for record in records]

        name = name.strip()
        if ":" in name:
            sys_part, _, ext_part = name.partition(":")
            sys = sys_part.strip()
            ext = ext_part.strip()
            or_domain = [("system_id.name", "ilike", sys), ("system_id.code", "ilike", sys)]
            dom = fields.Domain.AND(
                [
                    base,
                    fields.Domain.OR([[condition] for condition in or_domain]),
                    [("external_id", operator, ext)],
                ]
            )
        else:
            dom = fields.Domain.AND([base, [("external_id", operator, name)]])

        records = self.search(dom, limit=limit)
        return [(record.id, record.display_name or "") for record in records]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self) -> None:
        if any(record.active for record in self):
            raise ValidationError("Cannot delete active external IDs. Please archive them first.")
