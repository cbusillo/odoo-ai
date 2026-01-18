from odoo import fields, models


class RepairBatchDeviceIssue(models.Model):
    _name = "repair.batch.device.issue"
    _description = "Repair Batch Device Issue"
    _order = "id desc"
    _rec_name = "issue_id"

    device_line_id = fields.Many2one(
        "repair.batch.device",
        required=True,
        ondelete="cascade",
    )
    issue_id = fields.Many2one(
        "repair.issue",
        ondelete="restrict",
        required=True,
    )
    is_confirmed = fields.Boolean()
