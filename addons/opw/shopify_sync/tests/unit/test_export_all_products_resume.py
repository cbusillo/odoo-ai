from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory, ShopifySyncFactory

from ...services.shopify.helpers import DEFAULT_DATETIME
from ...services.shopify.sync.exporters.product_exporter import ProductExporter


@common.tagged(*common.UNIT_TAGS)
class TestExportAllProductsResume(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.products = [ProductFactory.create(self.env).product_variant_id for _ in range(3)]

    def test_export_all_products_captures_initial_batch_once(self) -> None:
        sync = ShopifySyncFactory.create(self.env, mode="export_all_products")

        with common.patch("odoo.addons.shopify_sync.services.shopify.ProductExporter") as exporter_class:
            exporter = exporter_class.return_value
            exporter._find_products_to_export.return_value = self.env["product.product"].browse([product.id for product in self.products])

            sync._run_export_all_products()

        exporter._find_products_to_export.assert_called_once_with(DEFAULT_DATETIME)
        exporter.export_products.assert_called_once()
        exported_products = exporter.export_products.call_args.args[0]
        self.assertEqual(sorted(exported_products.ids), sorted(product.id for product in self.products))
        self.assertEqual(sync.total_count, len(self.products))
        self.assertEqual(sorted(sync.odoo_products_to_sync.ids), sorted(product.id for product in self.products))

    def test_export_all_products_retry_uses_remaining_batch(self) -> None:
        sync = ShopifySyncFactory.create(
            self.env,
            mode="export_all_products",
            total_count=len(self.products),
            odoo_products_to_sync=[(6, 0, [self.products[1].id, self.products[2].id])],
        )

        with common.patch("odoo.addons.shopify_sync.services.shopify.ProductExporter") as exporter_class:
            exporter = exporter_class.return_value

            sync._run_export_all_products()

        exporter._find_products_to_export.assert_not_called()
        exporter.export_products.assert_called_once()
        exported_products = exporter.export_products.call_args.args[0]
        self.assertEqual(sorted(exported_products.ids), sorted([self.products[1].id, self.products[2].id]))
        self.assertEqual(sync.total_count, len(self.products))

    def test_mark_export_all_product_complete_removes_product_from_pending_batch(self) -> None:
        sync = ShopifySyncFactory.create(
            self.env,
            mode="export_all_products",
            odoo_products_to_sync=[(6, 0, [product.id for product in self.products])],
        )
        exporter = ProductExporter(self.env, sync)

        exporter._mark_export_all_product_complete(self.products[0])

        self.assertEqual(sorted(sync.odoo_products_to_sync.ids), sorted([self.products[1].id, self.products[2].id]))

    def test_mark_export_all_product_complete_keeps_product_when_reexport_is_flagged(self) -> None:
        sync = ShopifySyncFactory.create(
            self.env,
            mode="export_all_products",
            odoo_products_to_sync=[(6, 0, [product.id for product in self.products])],
        )
        exporter = ProductExporter(self.env, sync)

        self.products[0].shopify_next_export = True
        exporter._mark_export_all_product_complete(self.products[0])

        self.assertEqual(sorted(sync.odoo_products_to_sync.ids), sorted(product.id for product in self.products))
