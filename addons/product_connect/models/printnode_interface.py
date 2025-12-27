import logging

from odoo import api, fields, models
from printnodeapi import Gateway
from printnodeapi.model import PrintJob, Printer

_logger = logging.getLogger(__name__)


class PrintNodeInterface(models.Model):
    _name = "printnode.interface"
    _inherit = ["notification.manager.mixin"]
    _description = "PrintNode Interface"
    _sql_constraints = [
        (
            "user_id_print_job_type_unique",
            "unique(user_id, print_job_type)",
            "Printer already selected for this job type and user",
        )
    ]

    printer_selection = fields.Selection(selection="get_printer_tuple", string="Printer")
    print_job_type = fields.Selection(
        selection=[
            ("product_label", "Product Label"),
            ("product_label_picture", "Product Label Picture"),
            ("motor_label", "Motor Label"),
            ("pull_list", "Pull List"),
        ],
        default="product_label",
    )
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    def get_gateway(self) -> Gateway:
        api_key = self.env["ir.config_parameter"].sudo().get_param("printnode.api_key")
        if not api_key:
            message = self.env._("No PrintNode API key found")
            self.notify_channel_on_error("PrintNode Error", message)
        return Gateway(apikey=api_key)

    def get_printers(self) -> list[Printer]:
        gateway = self.get_gateway()
        printers = gateway.printers()
        if not printers:
            message = self.env._("No printers found on PrintNode")
            self.notify_channel_on_error("PrintNode Error", message)
        return printers

    def get_printer_tuple(self) -> list[tuple[int, str]]:
        printers = self.get_printers()
        return [(printer.id, printer.name) for printer in printers]

    @api.model
    def print_label(
        self,
        label_data: str | bytes,
        odoo_job_type: str,
        copies: int = 1,
        job_name: str = "Odoo Label",
    ) -> list[PrintJob] | None:
        gateway = self.get_gateway()
        interface_record = self.env["printnode.interface"].search(
            [
                ("user_id", "=", self.env.user.id),
                ("print_job_type", "=", odoo_job_type),
            ],
            limit=1,
        )
        if not interface_record:
            _logger.error(f"No printer configured for job type {odoo_job_type} and user {self.env.user.name}")
            return None
        printer_id = interface_record.printer_selection
        if not printer_id:
            _logger.error(f"Printer not selected for job type {odoo_job_type} and user {self.env.user.name}")
            return None

        print_jobs: list[PrintJob] = []
        print_job_params: dict[str, str | bytes]
        if isinstance(label_data, str):
            print_job_params = {"base64": label_data}
        elif isinstance(label_data, bytes):
            print_job_params = {"binary": label_data}
        else:
            _logger.error("Invalid label data type")
            return None
        try:
            for _ in range(copies):
                print_job = gateway.PrintJob(
                    printer=int(printer_id),
                    title=job_name,
                    job_type="raw",
                    **print_job_params,
                )
                print_jobs.append(print_job)

        except LookupError as error:
            _logger.exception(f"Error printing label: {error}")

        return print_jobs
