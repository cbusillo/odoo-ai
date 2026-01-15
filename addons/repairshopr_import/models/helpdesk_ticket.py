from odoo import models


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _inherit = ["helpdesk.ticket", "external.id.mixin"]
    _description = "Helpdesk Ticket"
