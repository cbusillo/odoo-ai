from odoo import models


class ExternalId(models.Model):
    _inherit = "external.id"

    def _skip_id_format_validation(self) -> bool:
        self.ensure_one()
        return super()._skip_id_format_validation() or (
            self.system_id.code == "shopify" and self.resource == "order_line"
        )
