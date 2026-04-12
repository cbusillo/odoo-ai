from odoo import fields

from ..common_imports import common
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import ProductFactory, ShopifySyncFactory


VALID_IMAGE_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aY6sAAAAASUVORK5CYII="


@common.tagged(*common.UNIT_TAGS)
class TestResetShopify(UnitTestCase):
    def _assert_shopify_state_cleared(self, product: "odoo.model.product_product") -> None:
        self.assertFalse(product.shopify_next_export)
        self.assertFalse(product.shopify_last_exported_at)
        self.assertEqual(product.shopify_next_export_quantity_change_amount, 0)
        self.assertFalse(product.shopify_created_at)
        self.assertFalse(product.get_external_system_id("shopify", "product"))
        self.assertFalse(product.get_external_system_id("shopify", "variant"))
        self.assertFalse(product.get_external_system_id("shopify", "condition"))
        self.assertFalse(product.get_external_system_id("shopify", "ebay_category"))

    def test_reset_shopify_requires_test_store_flag(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "")
        sync = ShopifySyncFactory.create(self.env, mode="reset_shopify")

        with common.patch("odoo.addons.shopify_sync.services.shopify.ProductDeleter") as product_deleter_class:
            with self.assertRaises(common.UserError):
                sync._run_reset_shopify()

        product_deleter_class.return_value.delete_all_products.assert_not_called()

    def test_reset_shopify_requires_test_store_flag_off_textual(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "False")
        sync = ShopifySyncFactory.create(self.env, mode="reset_shopify")

        with common.patch("odoo.addons.shopify_sync.services.shopify.ProductDeleter") as product_deleter_class:
            with self.assertRaises(common.UserError):
                sync._run_reset_shopify()

        product_deleter_class.return_value.delete_all_products.assert_not_called()

    def test_reset_shopify_clears_archived_products_and_shopify_identifiers(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "1")
        sync = ShopifySyncFactory.create(self.env, mode="reset_shopify")
        archived_timestamp = fields.Datetime.now()

        active_product = ProductFactory.create(
            self.env,
            shopify_product_id="111",
            shopify_variant_id="112",
            shopify_condition_id="113",
            shopify_ebay_category_id="114",
        ).product_variant_id
        archived_product = ProductFactory.create(
            self.env,
            shopify_product_id="211",
            shopify_variant_id="212",
            shopify_condition_id="213",
            shopify_ebay_category_id="214",
        ).product_variant_id
        archived_product.with_context(active_test=False).write(
            {
                "active": False,
                "shopify_next_export": True,
                "shopify_last_exported_at": archived_timestamp,
                "shopify_next_export_quantity_change_amount": 7,
                "shopify_created_at": archived_timestamp,
            }
        )
        active_product.write(
            {
                "shopify_next_export": True,
                "shopify_last_exported_at": archived_timestamp,
                "shopify_next_export_quantity_change_amount": 5,
                "shopify_created_at": archived_timestamp,
            }
        )
        image = self.env["product.image"].create(
            {
                "name": "Reset image",
                "image_1920": VALID_IMAGE_BASE64,
                "product_tmpl_id": active_product.product_tmpl_id.id,
            }
        )
        image.set_external_id("shopify", "311", resource="media")

        with common.patch("odoo.addons.shopify_sync.services.shopify.ProductDeleter") as product_deleter_class:
            sync._run_reset_shopify()

        product_deleter_class.return_value.delete_all_products.assert_called_once()

        active_product.invalidate_recordset()
        archived_product.invalidate_recordset()
        image.invalidate_recordset()

        archived_product = self.env["product.product"].with_context(active_test=False).browse(archived_product.id)

        self._assert_shopify_state_cleared(active_product)
        self._assert_shopify_state_cleared(archived_product)

        self.assertFalse(image.get_external_system_id("shopify", "media"))
