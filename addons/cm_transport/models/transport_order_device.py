from odoo import api, fields, models

TRANSPORT_MOVEMENT_TYPES = [
    ("in", "Inbound"),
    ("out", "Outbound"),
]


class TransportOrderDevice(models.Model):
    _name = "service.transport.order.device"
    _description = "Transport Order Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "transport_order, id"

    transport_order = fields.Many2one(
        "service.transport.order",
        required=True,
        ondelete="cascade",
    )
    device = fields.Many2one(
        "service.device",
        required=True,
        ondelete="restrict",
    )
    verification_scan = fields.Char(tracking=True)
    scan_date = fields.Datetime(tracking=True)
    movement_type = fields.Selection(
        TRANSPORT_MOVEMENT_TYPES,
        required=True,
        default=lambda self: self.env.context.get("default_movement_type"),
    )

    @api.onchange("verification_scan")
    def _onchange_verification_scan(self) -> None:
        if self.verification_scan:
            self.scan_date = fields.Datetime.now()
