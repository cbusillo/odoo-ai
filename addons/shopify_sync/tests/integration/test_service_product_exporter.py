import base64
from types import SimpleNamespace

from odoo import fields
from test_support.tests.shared.sync_doubles import DummySyncRecord

from ..common_imports import common

from ...services.shopify.sync.exporters.product_exporter import ProductExporter
from ...services.shopify import helpers as _helpers_module
from ...services.shopify.helpers import ShopifyApiError
from ...services.shopify.gql import (
    ProductSetProductSetProductResourcePublicationsV2NodesPublication,
    ProductSetProductSetProductResourcePublicationsV2Nodes,
)
from ..fixtures.base import IntegrationTestCase


class DummyPublication(ProductSetProductSetProductResourcePublicationsV2NodesPublication):
    def __init__(self, gid: str) -> None:
        super().__init__(id=gid, publication=type("P", (), {"id": gid})())


class DummyPublicationNode(ProductSetProductSetProductResourcePublicationsV2Nodes):
    def __init__(self, gid: str) -> None:
        publication = DummyPublication(gid)
        super().__init__(publication=publication)


@common.tagged(*common.INTEGRATION_TAGS)
class TestProductExporter(IntegrationTestCase):
    @staticmethod
    def _get_valid_image_base64() -> str:
        image_data = bytes(
            [
                0x89,
                0x50,
                0x4E,
                0x47,
                0x0D,
                0x0A,
                0x1A,
                0x0A,
                0x00,
                0x00,
                0x00,
                0x0D,
                0x49,
                0x48,
                0x44,
                0x52,
                0x00,
                0x00,
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x01,
                0x08,
                0x02,
                0x00,
                0x00,
                0x00,
                0x90,
                0x77,
                0x53,
                0xDE,
                0x00,
                0x00,
                0x00,
                0x0C,
                0x49,
                0x44,
                0x41,
                0x54,
                0x08,
                0xD7,
                0x63,
                0xF8,
                0xCF,
                0xC0,
                0x00,
                0x00,
                0x03,
                0x01,
                0x01,
                0x00,
                0x18,
                0xDD,
                0x8D,
                0xB1,
                0x00,
                0x00,
                0x00,
                0x00,
                0x49,
                0x45,
                0x4E,
                0x44,
                0xAE,
                0x42,
                0x60,
                0x82,
            ]
        )
        return base64.b64encode(image_data).decode()

    def setUp(self) -> None:
        super().setUp()
        self.exporter = ProductExporter(self.env, DummySyncRecord())

        from ..fixtures.factories import ProductFactory

        self.test_products = []
        for i in range(3):
            product_template = ProductFactory.create(
                self.env,
                list_price=100.0 + (i * 10),
            )
            self.test_products.append(product_template.product_variant_id)

    def test_metafield_from_id_value_key(self) -> None:
        result = ProductExporter.metafield_from_id_value_key("5", "k", "v", "text")
        self.assertEqual(result.namespace, "custom")
        self.assertEqual(result.key, "k")
        self.assertEqual(result.value, "v")
        self.assertEqual(result.type_, "text")
        self.assertEqual(str(result.id), "gid://shopify/Metafield/5")

    def test_is_published_on_channel(self) -> None:
        gid = "gid://shopify/Publication/" + str(next(iter(_helpers_module.PUBLICATION_CHANNELS.values())))
        publication = DummyPublication(gid)
        self.assertTrue(ProductExporter.is_published_on_channel(publication))
        publication.id = "gid://shopify/Publication/999"
        self.assertFalse(ProductExporter.is_published_on_channel(publication))

    def test_is_published_on_all_channels(self) -> None:
        values = list(_helpers_module.PUBLICATION_CHANNELS.values())
        channels = [DummyPublicationNode(f"gid://shopify/Publication/{v}") for v in values]
        self.assertTrue(self.exporter.is_published_on_all_channels(channels))
        channels.append(DummyPublicationNode("gid://shopify/Publication/999"))
        self.assertFalse(self.exporter.is_published_on_all_channels(channels))

    def test_publish_product(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "")
        self.exporter.service._client = common.MagicMock()
        self.exporter._publish_product("gid")
        self.exporter.service.client.update_publications.assert_called_once()

    def test_publish_product_skipped_on_test_store(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "1")
        self.exporter.service._client = common.MagicMock()
        self.exporter._publish_product("gid")
        self.exporter.service.client.update_publications.assert_not_called()

    def test_find_products_to_export(self) -> None:
        prod1 = self.test_products[0]  # This is a product.product
        prod1.is_ready_for_sale = True
        prod1.is_published = True
        setattr(prod1, "shopify_next_export", True)

        prod2 = self.test_products[1]  # This is a product.product
        prod2.write(
            {
                "is_ready_for_sale": True,
                "is_published": True,
                "sale_ok": False,
            }
        )

        prod3 = self.test_products[2]  # This is a product.product
        prod3.is_ready_for_sale = True
        prod3.is_published = True
        setattr(prod3, "shopify_last_exported_at", fields.Datetime.now() + common.timedelta(days=1))

        result = self.exporter._find_products_to_export()
        self.assertIn(prod1, result)
        self.assertNotIn(prod2, result)
        self.assertNotIn(prod3, result)

    def test_verify_shopify_media_for_reorder_preserves_product_ids_when_reorder_verification_fails(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        image = self.env["product.image"].create(
            {
                "name": "Image 1",
                "image_1920": self._get_valid_image_base64(),
                "product_tmpl_id": product.product_tmpl_id.id,
            }
        )
        image.set_external_id("shopify", "111", resource="media")

        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.get_products.return_value = common.Mock(nodes=[])

        should_reorder = self.exporter._verify_shopify_media_for_reorder(
            product,
            "555",
            product.images.sorted(key=lambda product_image: product_image.sequence),
        )

        self.assertFalse(should_reorder)
        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(image.get_external_system_id("shopify", "media"))
        self.assertTrue(product.shopify_next_export)

    def test_export_one_raises_for_missing_remote_product_and_preserves_mappings(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        shopify_error = common.Mock()
        shopify_error.message = "Product does not exist"
        shopify_response.user_errors = [shopify_error]
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)

    def test_export_one_raises_for_unconfirmed_missing_remote_product(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        shopify_error = common.Mock()
        shopify_error.message = "Title can't be blank"
        shopify_response.user_errors = [shopify_error]
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)

    def test_export_one_raises_for_mixed_product_set_user_errors(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        not_found_error = common.Mock()
        not_found_error.message = "Product does not exist"
        validation_error = common.Mock()
        validation_error.message = "Title can't be blank"
        shopify_response.user_errors = [not_found_error, validation_error]
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)

    def test_export_one_raises_when_missing_product_has_no_user_errors(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        shopify_response.user_errors = []
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")

    def test_export_one_handles_dict_user_errors_in_missing_product_response(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        shopify_response.user_errors = [{"message": "Product does not exist"}]
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)

    def test_export_one_handles_none_user_errors_in_missing_product_response(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = common.Mock()
        shopify_response.product = None
        shopify_response.user_errors = None
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)

    def test_export_one_handles_missing_user_errors_attribute_in_missing_product_response(self) -> None:
        from ..fixtures.factories import ProductFactory

        product = ProductFactory.create(
            self.env,
            shopify_product_id="555",
            shopify_variant_id="556",
            shopify_condition_id="557",
            shopify_ebay_category_id="558",
        ).product_variant_id
        self.exporter._map_odoo_product_to_shopify_product_set_input = common.MagicMock(return_value=common.Mock())
        shopify_response = SimpleNamespace(product=None)
        self.exporter.service._client = common.MagicMock()
        self.exporter.service.client.product_set.return_value = shopify_response

        with self.assertRaises(ShopifyApiError):
            self.exporter._export_one(product)

        self.assertEqual(product.get_external_system_id("shopify", "product"), "555")
        self.assertEqual(product.get_external_system_id("shopify", "variant"), "556")
        self.assertEqual(product.get_external_system_id("shopify", "condition"), "557")
        self.assertEqual(product.get_external_system_id("shopify", "ebay_category"), "558")
        self.assertFalse(product.shopify_next_export)
