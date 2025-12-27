from odoo import fields, models

REPAIR_BATCH_PART_USAGE_STATES = [
    ("used", "Used"),
    ("not_needed", "Not Needed"),
]


class RepairBatchDevicePart(models.Model):
    _name = "repair.batch.device.part"
    _description = "Repair Batch Device Part"
    _order = "id desc"
    _rec_name = "product_id"

    device_line_id = fields.Many2one(
        "repair.batch.device",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        ondelete="restrict",
    )
    is_pulled = fields.Boolean()
    usage_state = fields.Selection(
        REPAIR_BATCH_PART_USAGE_STATES,
        default=REPAIR_BATCH_PART_USAGE_STATES[0][0],
    )
