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

    @api.ondelete(at_uninstall=False)
    def _unlink_prevent_when_has_ids(self) -> None:
        for rec in self:
            if rec.external_ids:
                raise ValidationError(
                    "Cannot delete an External System that still has External IDs. "
                    "Archive the system or remove the related IDs first."
                )
