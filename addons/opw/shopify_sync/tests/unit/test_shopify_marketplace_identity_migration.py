from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory
from ...hooks import _migrate_external_ids_for_system, _migrate_template_shopify_product_ids


@common.tagged(*common.UNIT_TAGS)
class TestShopifyMarketplaceIdentityMigration(UnitTestCase):
    def _column_exists(self, table_name: str, column_name: str) -> bool:
        self.env.cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = %s
             LIMIT 1
            """,
            (table_name, column_name),
        )
        return bool(self.env.cr.fetchone())

    def test_product_variant_migration_reclaims_archived_same_model_mapping(self) -> None:
        archived_template = ProductFactory.create(self.env, name="Archived Shopify Product")
        migrated_template = ProductFactory.create(self.env, name="Migrated Shopify Product")
        archived_variant = archived_template.product_variant_id
        migrated_variant = migrated_template.product_variant_id

        archived_variant.set_external_id("shopify", "555", resource="product")
        archived_variant.get_external_id_record("shopify", "product", active_only=False).active = False

        self.env.cr.execute("ALTER TABLE product_product ADD COLUMN IF NOT EXISTS shopify_product_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE product_product SET shopify_product_id = %s WHERE id = %s",
            ("555", migrated_variant.id),
        )

        drop_candidates = _migrate_external_ids_for_system(
            self.env,
            model_name="product.product",
            table_name="product_product",
            system_code="shopify",
            field_resource_map={"shopify_product_id": "product"},
        )

        self.assertEqual(drop_candidates, {"shopify_product_id"})
        migrated_variant.invalidate_recordset()
        self.assertEqual(migrated_variant.external.shopify.product.id, "555")
        archived_variant.invalidate_recordset()
        self.assertFalse(archived_variant.external.shopify.product.id)

    def test_template_shopify_product_ids_migrate_consistent_value(self) -> None:
        product_template = ProductFactory.create_with_variants(
            self.env,
            variant_count=2,
            name="Consistent Shopify Product",
        )
        variant_records = product_template.product_variant_ids.sorted("id")
        canonical_variant = variant_records[0]

        self.env.cr.execute("ALTER TABLE product_template ADD COLUMN IF NOT EXISTS shopify_product_id VARCHAR")
        self.env.cr.execute("ALTER TABLE product_product ADD COLUMN IF NOT EXISTS shopify_product_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE product_template SET shopify_product_id = %s WHERE id = %s",
            ("777", product_template.id),
        )
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE product_product SET shopify_product_id = %s WHERE product_tmpl_id = %s",
            ("777", product_template.id),
        )

        drop_candidates = _migrate_template_shopify_product_ids(self.env)

        self.assertEqual(
            drop_candidates,
            {
                "product_template": {"shopify_product_id"},
                "product_product": {"shopify_product_id"},
            },
        )
        canonical_variant.invalidate_recordset()
        self.assertEqual(canonical_variant.external.shopify.product.id, "777")

    def test_template_shopify_product_ids_preserve_columns_for_mixed_variant_ids(self) -> None:
        product_template = ProductFactory.create_with_variants(
            self.env,
            variant_count=2,
            name="Mixed Shopify Product",
        )
        variant_records = product_template.product_variant_ids.sorted("id")

        self.env.cr.execute("ALTER TABLE product_template ADD COLUMN IF NOT EXISTS shopify_product_id VARCHAR")
        self.env.cr.execute("ALTER TABLE product_product ADD COLUMN IF NOT EXISTS shopify_product_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE product_product SET shopify_product_id = %s WHERE id = %s",
            ("701", variant_records[0].id),
        )
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE product_product SET shopify_product_id = %s WHERE id = %s",
            ("702", variant_records[1].id),
        )

        drop_candidates = _migrate_template_shopify_product_ids(self.env)

        self.assertEqual(drop_candidates, {})
        self.assertTrue(self._column_exists("product_template", "shopify_product_id"))
        self.assertTrue(self._column_exists("product_product", "shopify_product_id"))
        for variant_record in variant_records:
            variant_record.invalidate_recordset()
            self.assertFalse(variant_record.external.shopify.product.id)
