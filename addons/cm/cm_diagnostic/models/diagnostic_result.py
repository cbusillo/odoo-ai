from odoo import fields, models

DIAGNOSTIC_RESULT_STATES = [
    ("pass", "Pass"),
    ("fail", "Fail"),
    ("not_applicable", "Not Applicable"),
]


class DiagnosticResult(models.Model):
    _name = "service.diagnostic.result"
    _description = "Diagnostic Result"
    _order = "diagnostic_order_device, test, id"

    diagnostic_order_device = fields.Many2one(
        "service.diagnostic.order.device",
        required=True,
        ondelete="cascade",
    )
    test = fields.Many2one(
        "service.diagnostic.test",
        required=True,
        ondelete="restrict",
    )
    result = fields.Selection(
        DIAGNOSTIC_RESULT_STATES,
        default=DIAGNOSTIC_RESULT_STATES[0][0],
        required=True,
    )
    notes = fields.Text()
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "diagnostic_result_attachment_rel",
        "result_id",
        "attachment_id",
        string="Evidence",
    )

    _sql_constraints = [
        (
            "diagnostic_result_unique",
            "unique(diagnostic_order_device, test)",
            "A test can only be used once per diagnostic device.",
        ),
    ]
