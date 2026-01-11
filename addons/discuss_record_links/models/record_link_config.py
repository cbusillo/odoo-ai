from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DiscussRecordLinkConfig(models.Model):
    _name = "discuss.record.link.config"
    _description = "Discuss Record Link Configuration"
    _order = "prefix"

    active = fields.Boolean(default=True)
    prefix = fields.Char(required=True, help="Short key used in the composer, e.g., 'pro' or 'po'.")
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        domain=[("transient", "=", False)],
        ondelete="cascade",
    )
    label = fields.Char(required=True, help="Group label shown in suggestions, e.g., 'Products'.")
    search_field_ids = fields.Many2many(
        "ir.model.fields",
        string="Search Fields",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['char','text','many2one','integer','float'])]",
        help="Fields used for ilike search tokens.",
    )
    display_template = fields.Text(
        default="{{ display_name }}",
        help="Template to render a suggestion label. Use {{ field_name }} placeholders.",
    )
    image_field_id = fields.Many2one(
        "ir.model.fields",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['binary'])]",
        help="Optional image field to display an avatar in results.",
        ondelete="set null",
    )
    limit = fields.Integer(default=8)

    _prefix_unique = models.Constraint("unique(prefix)", "Prefix must be unique.")

    @api.constrains("search_field_ids", "model_id")
    def _check_search_fields_model(self) -> None:
        for rec in self:
            if any(f.model_id != rec.model_id for f in rec.search_field_ids):
                raise ValidationError("Search fields must belong to the selected model.")

    @api.constrains("image_field_id", "model_id")
    def _check_image_field_model(self) -> None:
        for rec in self:
            if rec.image_field_id and rec.image_field_id.model_id != rec.model_id:
                raise ValidationError("Image field must belong to the selected model.")
