from odoo import fields, models


class Device(models.Model):
    _name = "device"
    _description = "Service Device"
    _inherit = ["mail.thread", "mail.activity.mixin", "external.id.mixin"]
    _order = "serial_number asc, id desc"

    _rec_name = "serial_number"

    serial_number = fields.Char(tracking=True)
    is_serial_unavailable = fields.Boolean(tracking=True)
    model = fields.Many2one(
        "device.model",
        required=True,
        ondelete="restrict",
    )
    owner = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )
    payer = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    bin = fields.Char()
    is_in_manufacturer_warranty = fields.Boolean()
    transport_orders = fields.One2many(
        "transport.order.device",
        "device",
    )
    intake_orders = fields.One2many(
        "intake.order.device",
        "device",
    )
    diagnostic_orders = fields.One2many(
        "diagnostic.order.device",
        "device",
    )
    repair_batch_lines = fields.One2many(
        "repair.batch.device",
        "device_id",
        string="Repair Batches",
    )

    invoices = fields.Many2many(
        "account.move",
        "cm_custom_device_account_move_rel",
        "device_id",
        "move_id",
        domain="[('move_type', 'in', ['out_invoice', 'out_refund'])]",
    )
