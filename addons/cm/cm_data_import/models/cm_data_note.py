from odoo import fields, models

NOTE_TYPES = [
    ("intake", "Intake"),
    ("diagnostic", "Diagnostic"),
    ("repair", "Repair"),
    ("quality_control", "Quality Control"),
    ("invoice", "Invoice"),
]


class CmDataNote(models.Model):
    _name = "integration.cm_data.note"
    _description = "CM Data Note"
    _inherit = ["external.id.mixin"]
    _order = "partner_id, note_type, sort_order, id"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    note_type = fields.Selection(
        NOTE_TYPES,
        required=True,
    )
    sub_name = fields.Char()
    notes = fields.Text()
    sort_order = fields.Integer()
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
    active = fields.Boolean(default=True)
