from ...migrations.product_type_external_identity import migrate_product_type_ebay_category_external_ids
from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestProductTypeExternalIdentityMigration(UnitTestCase):
    def test_migration_moves_ebay_category_and_condition_to_external_ids_and_drops_columns(self) -> None:
        product_type = self.env["product.type"].create({"name": "Motors"})
        product_condition = self.env["product.condition"].search([("code", "=", "used")], limit=1)
        self.assertTrue(product_condition)

        self.env.cr.execute("ALTER TABLE product_type ADD COLUMN IF NOT EXISTS ebay_category_id INTEGER")
        self.env.cr.execute("ALTER TABLE product_condition ADD COLUMN IF NOT EXISTS ebay_condition_id INTEGER")
        self.env.cr.execute(
            "UPDATE product_type SET ebay_category_id = %s WHERE id = %s",
            (123456, product_type.id),
        )
        self.env.cr.execute(
            "UPDATE product_condition SET ebay_condition_id = %s WHERE id = %s",
            (3000, product_condition.id),
        )

        migrate_product_type_ebay_category_external_ids(self.env.cr)

        product_type.invalidate_recordset()
        product_condition.invalidate_recordset()
        self.assertEqual(product_type.external_reference.id, "123456")
        self.assertEqual(self.env["product.type"].search_by_bound_external_id("123456"), product_type)
        self.assertEqual(product_condition.external_reference.id, "3000")
        self.assertEqual(self.env["product.condition"].search_by_bound_external_id("3000"), product_condition)

        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE (table_name = 'product_type' AND column_name = 'ebay_category_id')
                OR (table_name = 'product_condition' AND column_name = 'ebay_condition_id')
            """
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_migration_raises_when_active_duplicate_exists(self) -> None:
        first_type = self.env["product.type"].create({"name": "First Type"})
        second_type = self.env["product.type"].create({"name": "Second Type"})
        first_type.external_reference.id = "123456"

        self.env.cr.execute("ALTER TABLE product_type ADD COLUMN IF NOT EXISTS ebay_category_id INTEGER")
        self.env.cr.execute(
            "UPDATE product_type SET ebay_category_id = %s WHERE id = %s",
            (123456, second_type.id),
        )

        with self.assertRaises(RuntimeError):
            migrate_product_type_ebay_category_external_ids(self.env.cr)
