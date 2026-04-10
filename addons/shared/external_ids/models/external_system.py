from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ExternalSystem(models.Model):
    _name = "external.system"
    _description = "External System Configuration"
    _order = "sequence, name"
    _rec_name = "name"

    name = fields.Char(required=True, help="Name of the external system (e.g., Discord, RepairShopr)")
    code = fields.Char(required=True, help="Unique code for the system (e.g., discord, repairshopr)")
    description = fields.Text(help="Description of the external system and its purpose")
    url = fields.Char(string="Base URL", help="Base URL of the external system")
    active = fields.Boolean(default=True, help="If unchecked, this system will not be available for selection")
    sequence = fields.Integer(default=10, help="Used to order the systems in views")
    id_format = fields.Char(help="Expected format or pattern for IDs in this system (e.g., regex pattern)")
    id_prefix = fields.Char(string="ID Prefix", help="Prefix to add when displaying the ID")
    applicable_model_ids = fields.Many2many(
        "ir.model",
        "external_system_ir_model_rel",
        "system_id",
        "model_id",
        string="Applies To Models",
        help="Optional: limit where this system is selectable. If empty, the system is available for all models.",
    )
    # Legacy template fields removed; use url_templates instead
    external_ids = fields.One2many("external.id", "system_id", string="External IDs")
    url_templates = fields.One2many("external.system.url", "system_id", string="URL Templates")
    external_id_count = fields.Integer(string="Number of Records", compute="_compute_external_id_count")

    _code_unique = models.Constraint("unique(code)", "System code must be unique!")
    _name_unique = models.Constraint("unique(name)", "System name must be unique!")

    @api.depends("external_ids")
    def _compute_external_id_count(self) -> None:
        for system in self:
            system.external_id_count = len(system.external_ids)

    @api.model_create_multi
    def create(self, vals_list: "list[odoo.values.external_system]") -> "odoo.model.external_system":
        seen_codes: set[str] = set()
        seen_names: set[str] = set()
        for vals in vals_list:
            code_raw = vals.get("code")
            code_value = str(code_raw or "").strip()
            if code_raw is not None:
                vals["code"] = code_value
            if code_value:
                if code_value in seen_codes or self.sudo().search_count([("code", "=", code_value)]):
                    raise ValidationError("System code must be unique!")
                seen_codes.add(code_value)
            name_raw = vals.get("name")
            name_value = str(name_raw or "").strip()
            if name_raw is not None:
                vals["name"] = name_value
            if name_value:
                if name_value in seen_names or self.sudo().search_count([("name", "=", name_value)]):
                    raise ValidationError("System name must be unique!")
                seen_names.add(name_value)
        return super().create(vals_list)

    @api.constrains("code")
    def _check_unique_code(self) -> None:
        for system in self:
            if not system.code:
                continue
            domain = [("code", "=", system.code)]
            if system.id:
                domain.append(("id", "!=", system.id))
            if self.sudo().search_count(domain):
                raise ValidationError("System code must be unique!")

    @api.constrains("name")
    def _check_unique_name(self) -> None:
        for system in self:
            if not system.name:
                continue
            domain = [("name", "=", system.name)]
            if system.id:
                domain.append(("id", "!=", system.id))
            if self.sudo().search_count(domain):
                raise ValidationError("System name must be unique!")

    @api.model
    def ensure_system(
        self,
        *,
        code: str,
        name: str,
        id_format: str | None = None,
        sequence: int | None = None,
        active: bool | None = None,
        url: str | None = None,
        applicable_model_xml_ids: tuple[str, ...] = (),
    ) -> "odoo.model.external_system":
        code = (code or "").strip()
        name = (name or "").strip()
        external_system_model = self.sudo().with_context(active_test=False)
        system = external_system_model.search([("code", "=", code)], limit=1)
        applicable_model_ids = self._resolve_applicable_model_ids(applicable_model_xml_ids)
        if not system:
            create_values: "odoo.values.external_system" = {
                "name": name,
                "code": code,
            }
            if id_format:
                create_values["id_format"] = id_format
            if sequence is not None:
                create_values["sequence"] = sequence
            if active is not None:
                create_values["active"] = active
            if url:
                create_values["url"] = url
            if applicable_model_ids:
                create_values["applicable_model_ids"] = [(6, 0, applicable_model_ids)]
            return external_system_model.create(create_values)

        update_values: "odoo.values.external_system" = {}
        if name and not system.name:
            update_values["name"] = name
        if url and not system.url:
            update_values["url"] = url
        if id_format and not system.id_format:
            update_values["id_format"] = id_format
        if sequence is not None and not system.sequence:
            update_values["sequence"] = sequence
        if active is True and not system.active:
            update_values["active"] = True
        if applicable_model_ids:
            current_model_ids = set(system.applicable_model_ids.ids)
            merged_model_ids = sorted(current_model_ids.union(applicable_model_ids))
            if set(merged_model_ids) != current_model_ids:
                update_values["applicable_model_ids"] = [(6, 0, merged_model_ids)]
        if update_values:
            system.write(update_values)
        return system

    @api.model
    def _resolve_applicable_model_ids(self, xml_ids: tuple[str, ...]) -> list[int]:
        model_id_list: list[int] = []
        for xml_id in xml_ids:
            record = self.env.ref(xml_id, raise_if_not_found=False)
            if record:
                model_id_list.append(record.id)
        return model_id_list

    @api.ondelete(at_uninstall=False)
    def _unlink_prevent_when_has_ids(self) -> None:
        for rec in self:
            if rec.external_ids:
                raise ValidationError(
                    "Cannot delete an External System that still has External IDs. "
                    "Archive the system or remove the related IDs first."
                )
