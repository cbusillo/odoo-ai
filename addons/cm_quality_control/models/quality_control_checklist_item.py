from odoo import fields, models

QUALITY_CONTROL_CHECKLIST_CATEGORIES = [
    ("paperwork", "Paperwork"),
    ("exterior", "Exterior"),
    ("power", "Power"),
    ("display", "Display"),
    ("connectivity", "Connectivity"),
    ("input", "Input"),
    ("camera_audio", "Camera / Audio"),
    ("other", "Other"),
]


class QualityControlChecklistItem(models.Model):
    _name = "service.quality.control.checklist.item"
    _description = "Quality Control Checklist Item"
    _inherit = ["external.id.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True)
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="cascade",
    )
    category = fields.Selection(
        QUALITY_CONTROL_CHECKLIST_CATEGORIES,
        default=QUALITY_CONTROL_CHECKLIST_CATEGORIES[-1][0],
        required=True,
    )
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
