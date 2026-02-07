from odoo import api, fields, models

TRANSPORT_ORDER_CLOSED_STATES = {"intake_complete"}


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "external.id.mixin"]
    _description = "Partner"

    is_repair_client = fields.Boolean()
    is_buyback_client = fields.Boolean()
    is_accessories_client = fields.Boolean()
    is_devices_client = fields.Boolean()
    availability_calendar = fields.Many2one(
        "resource.calendar",
        ondelete="set null",
    )
    unavailability_calendar = fields.Many2one(
        "resource.calendar",
        ondelete="set null",
    )
    average_time_on_location_per_device = fields.Float(compute="_compute_average_time")
    devices = fields.One2many("service.device", "owner")
    devices_at_depot = fields.Many2many(
        "service.device",
        compute="_compute_devices_at_depot",
    )
    transport_orders = fields.One2many("service.transport.order", "client")
    intake_orders = fields.One2many("service.intake.order", "client")
    diagnostic_orders = fields.Many2many(
        "service.diagnostic.order",
        compute="_compute_diagnostic_orders",
    )
    qc_orders = fields.Many2many(
        "service.quality.control.order.device",
        compute="_compute_qc_orders",
    )
    repair_batch_devices = fields.Many2many(
        "service.repair.batch.device",
        compute="_compute_repair_batch_devices",
    )

    repair_batches = fields.Many2many(
        "service.repair.batch",
        "partner_service_repair_batch_rel",
        "partner_id",
        "batch_id",
    )
    invoices = fields.Many2many(
        "account.move",
        "partner_account_move_rel",
        "partner_id",
        "move_id",
        string="Customer Invoices",
        domain="[('move_type', 'in', ['out_invoice', 'out_refund'])]",
    )

    @api.depends("transport_orders.arrival_date", "transport_orders.departure_date")
    def _compute_average_time(self) -> None:
        for partner in self:
            orders = partner.transport_orders
            durations = [
                abs((order.arrival_date - order.departure_date).total_seconds())
                for order in orders
                if order.arrival_date and order.departure_date
            ]
            if durations:
                partner.average_time_on_location_per_device = sum(durations) / len(durations) / 3600.0
            else:
                partner.average_time_on_location_per_device = 0.0

    @api.depends("transport_orders.state", "transport_orders.devices.device")
    def _compute_devices_at_depot(self) -> None:
        for partner in self:
            active_orders = partner.transport_orders.filtered(lambda order: order.state not in TRANSPORT_ORDER_CLOSED_STATES)
            partner.devices_at_depot = active_orders.mapped("devices.device")

    @api.depends("devices.diagnostic_orders.diagnostic_order")
    def _compute_diagnostic_orders(self) -> None:
        for partner in self:
            partner.diagnostic_orders = partner.devices.mapped("diagnostic_orders.diagnostic_order")

    @api.depends("devices.quality_control_order_devices.state")
    def _compute_qc_orders(self) -> None:
        for partner in self:
            partner.qc_orders = partner.devices.mapped("quality_control_order_devices").filtered(
                lambda line: line.state in {"pending", "started"}
            )

    @api.depends("devices.repair_batch_lines")
    def _compute_repair_batch_devices(self) -> None:
        for partner in self:
            partner.repair_batch_devices = partner.devices.mapped("repair_batch_lines")
