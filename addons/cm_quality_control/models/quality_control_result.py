from odoo import fields, models

QUALITY_CONTROL_RESULT_STATES = [
    ("pass", "Pass"),
    ("fail", "Fail"),
    ("not_applicable", "Not Applicable"),
]


class QualityControlResult(models.Model):
    _name = "service.quality.control.result"
    _description = "Quality Control Result"
    _order = "quality_control_order_device, checklist_item, id"

    quality_control_order_device = fields.Many2one(
        "service.quality.control.order.device",
        required=True,
        ondelete="cascade",
    )
    checklist_item = fields.Many2one(
        "service.quality.control.checklist.item",
        required=True,
        ondelete="restrict",
    )
    result = fields.Selection(
        QUALITY_CONTROL_RESULT_STATES,
        default=QUALITY_CONTROL_RESULT_STATES[0][0],
        required=True,
    )
    notes = fields.Text()
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "quality_control_result_attachment_rel",
        "result_id",
        "attachment_id",
        string="Evidence",
    )

    _sql_constraints = [
        (
            "quality_control_result_unique",
            "unique(quality_control_order_device, checklist_item)",
            "A checklist item can only be used once per quality control device.",
        ),
    ]
