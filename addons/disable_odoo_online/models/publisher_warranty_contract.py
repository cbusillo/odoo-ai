from datetime import timedelta

from odoo import fields, models


class PublisherWarrantyContract(models.AbstractModel):
    _inherit = "publisher_warranty.contract"

    def update_notification(self, cron_mode: bool = True) -> bool:
        _ = cron_mode
        expiration_date = fields.Datetime.now() + timedelta(days=90)
        expiration_str = fields.Datetime.to_string(expiration_date)
        set_param = self.env["ir.config_parameter"].sudo().set_param
        set_param("database.expiration_date", expiration_str)
        return True
