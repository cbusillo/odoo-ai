from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestAutopostBillsMigration(UnitTestCase):
    def test_base_partner_has_autopost_bills(self) -> None:
        base_partner = self.env["res.partner"].browse(1)

        self.assertEqual(base_partner.autopost_bills, "ask", "Base partner should have autopost_bills='ask' after migration")

        base_partner.write({"phone": "+1234567890"})

    def test_create_partner_without_autopost_bills(self) -> None:
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner After Migration",
            }
        )

        self.assertEqual(partner.autopost_bills, "ask", "New partners should get default autopost_bills='ask'")

    def test_no_null_autopost_bills(self) -> None:
        self.env.cr.execute("SELECT COUNT(*) FROM res_partner WHERE autopost_bills IS NULL")
        null_count = self.env.cr.fetchone()[0]

        self.assertEqual(null_count, 0, "No partners should have NULL autopost_bills after migration")
