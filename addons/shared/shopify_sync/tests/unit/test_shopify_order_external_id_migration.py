from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import PartnerFactory, ProductFactory, SaleOrderFactory, SaleOrderLineFactory
from ...migrations.shopify_order_identity import (
    migrate_shipstation_order_identity_external_ids,
    migrate_shopify_order_identity_external_ids,
)


@common.tagged(*common.UNIT_TAGS)
class TestShopifyOrderExternalIdMigration(UnitTestCase):
    def test_marketplace_migration_moves_order_and_line_shopify_ids_to_external_ids(self) -> None:
        partner = PartnerFactory.create(self.env, name="Migration Customer")
        product = ProductFactory.create(self.env, name="Migration Product").product_variant_id
        order = SaleOrderFactory.create(
            self.env,
            partner_id=partner.id,
            source_platform="shopify",
        )
        order_line = SaleOrderLineFactory.create(
            self.env,
            order_id=order.id,
            product_id=product.id,
            product_uom_qty=1,
            price_unit=25.0,
            name="Migration line",
        )

        self.env.cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS shopify_order_id VARCHAR")
        self.env.cr.execute("ALTER TABLE sale_order_line ADD COLUMN IF NOT EXISTS shopify_order_line_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE sale_order SET shopify_order_id = %s WHERE id = %s",
            ("123456789", order.id),
        )
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE sale_order_line SET shopify_order_line_id = %s WHERE id = %s",
            ("tax:123456789:Sales Tax", order_line.id),
        )

        migrate_shopify_order_identity_external_ids(self.env)

        order.invalidate_recordset()
        order_line.invalidate_recordset()

        self.assertEqual(order.external_reference.id, "123456789")
        self.assertEqual(order_line.external_reference.id, "tax:123456789:Sales Tax")
        external_id_model = self.env["external.id"].sudo()
        order_external_id = external_id_model.search(
            [
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
                ("resource", "=", "order"),
                ("external_id", "=", "123456789"),
            ],
            limit=1,
        )
        order_line_external_id = external_id_model.search(
            [
                ("res_model", "=", "sale.order.line"),
                ("res_id", "=", order_line.id),
                ("resource", "=", "order_line"),
                ("external_id", "=", "tax:123456789:Sales Tax"),
            ],
            limit=1,
        )
        self.assertTrue(order_external_id)
        self.assertTrue(order_line_external_id)

        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'sale_order'
               AND column_name = 'shopify_order_id'
            """
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_marketplace_migration_normalizes_shopify_order_id(self) -> None:
        partner = PartnerFactory.create(self.env, name="Shopify Migration Customer")
        order = SaleOrderFactory.create(
            self.env,
            partner_id=partner.id,
            source_platform="shopify",
        )

        self.env.cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS shopify_order_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE sale_order SET shopify_order_id = %s WHERE id = %s",
            ("gid://shopify/Order/SHO1234", order.id),
        )

        migrate_shopify_order_identity_external_ids(self.env)

        order.invalidate_recordset()
        external_id_model = self.env["external.id"].sudo()
        order_external_id = external_id_model.search(
            [
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
                ("resource", "=", "order"),
                ("external_id", "=", "1234"),
            ],
            limit=1,
        )
        self.assertTrue(order_external_id)

        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'sale_order'
               AND column_name = 'shopify_order_id'
            """
        )
        self.assertFalse(self.env.cr.fetchone())
        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'sale_order_line'
               AND column_name = 'shopify_order_line_id'
            """
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_marketplace_migration_moves_ebay_order_id_to_external_ids(self) -> None:
        partner = PartnerFactory.create(self.env, name="eBay Migration Customer")
        order = SaleOrderFactory.create(
            self.env,
            partner_id=partner.id,
            source_platform="ebay",
        )

        self.env.cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS ebay_order_id VARCHAR")
        self.env.cr.execute(
            "UPDATE sale_order SET ebay_order_id = %s WHERE id = %s",
            ("14-13240-64196", order.id),
        )

        migrate_shopify_order_identity_external_ids(self.env)

        order.invalidate_recordset()
        self.assertEqual(order.external.ebay.order.id, "14-13240-64196")

        external_id_model = self.env["external.id"].sudo()
        ebay_order_external_id = external_id_model.search(
            [
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
                ("system_id.code", "=", "ebay"),
                ("resource", "=", "order"),
                ("external_id", "=", "14-13240-64196"),
            ],
            limit=1,
        )
        self.assertTrue(ebay_order_external_id)

        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'sale_order'
               AND column_name = 'ebay_order_id'
            """
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_marketplace_migration_reclaims_archived_same_model_mapping(self) -> None:
        archived_order = SaleOrderFactory.create(
            self.env,
            partner_id=PartnerFactory.create(self.env, name="Archived Shopify Customer").id,
            source_platform="shopify",
        )
        migrated_order = SaleOrderFactory.create(
            self.env,
            partner_id=PartnerFactory.create(self.env, name="Migrated Shopify Customer").id,
            source_platform="shopify",
        )
        archived_order.external_reference.id = "123456789"
        archived_order.external_id_record.active = False

        self.env.cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS shopify_order_id VARCHAR")
        # noinspection SqlResolve
        self.env.cr.execute(
            "UPDATE sale_order SET shopify_order_id = %s WHERE id = %s",
            ("123456789", migrated_order.id),
        )

        migrate_shopify_order_identity_external_ids(self.env)

        migrated_order.invalidate_recordset()
        self.assertEqual(migrated_order.external_reference.id, "123456789")
        archived_order.invalidate_recordset()
        self.assertFalse(archived_order.external_reference.id)

    def test_shipstation_migration_moves_order_id_to_external_ids(self) -> None:
        partner = PartnerFactory.create(self.env, name="ShipStation Migration Customer")
        order = SaleOrderFactory.create(
            self.env,
            partner_id=partner.id,
            source_platform="manual",
        )

        self.env.cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS shipstation_order_id VARCHAR")
        self.env.cr.execute(
            "UPDATE sale_order SET shipstation_order_id = %s WHERE id = %s",
            ("SS-5001", order.id),
        )

        migrate_shipstation_order_identity_external_ids(self.env)

        order.invalidate_recordset()
        self.assertEqual(order.external["shipstation"]["order"].id, "SS-5001")

        external_id_model = self.env["external.id"].sudo()
        shipstation_external_id = external_id_model.search(
            [
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
                ("system_id.code", "=", "shipstation"),
                ("resource", "=", "order"),
                ("external_id", "=", "SS-5001"),
            ],
            limit=1,
        )
        self.assertTrue(shipstation_external_id)

        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'sale_order'
               AND column_name = 'shipstation_order_id'
            """
        )
        self.assertFalse(self.env.cr.fetchone())
