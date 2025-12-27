from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("-at_install", "post_install")
class TestPublisherWarrantyContract(TransactionCase):
    def test_update_notification_sets_expiration_param(self) -> None:
        config = self.env["ir.config_parameter"].sudo()

        config.set_param("database.expiration_date", "")
        result = self.env["publisher_warranty.contract"].update_notification(cron_mode=False)

        self.assertTrue(result, "update_notification() should return True")

        expiration_str = config.get_param("database.expiration_date")
        self.assertTrue(expiration_str, "Param database.expiration_date was not set")

        expiration_date = fields.Datetime.from_string(expiration_str)
        now = fields.Datetime.now()

        lower_bound = now + timedelta(days=85)
        upper_bound = now + timedelta(days=95)

        self.assertTrue(
            lower_bound <= expiration_date <= upper_bound,
            f"Expiration date {expiration_date} is not ~90 days in the future (expected between {lower_bound} and {upper_bound})",
        )
