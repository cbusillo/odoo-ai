import base64

from ..common_imports import datetime, patch, tagged, INTEGRATION_TAGS
from ..test_helpers import generate_unique_sku

from ...services.shopify.gql import MediaStatus, ProductStatus, ProductFields
from ...services.shopify.helpers import ShopifyDataError
from ...services.shopify.sync.importers.product_importer import ProductImporter
from ..fixtures.shopify_responses import (
    create_shopify_metafield,
    create_shopify_product_image,
    create_shopify_product_response,
    create_shopify_variant_response as create_shopify_product_variant,
)
from ..fixtures.test_service_utils import create_mock_simple_response
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ProductFactory, ShopifySyncFactory


@tagged(*INTEGRATION_TAGS)
class TestProductImporter(IntegrationTestCase):
    @classmethod
    def _get_unique_sku(cls) -> str:
        return generate_unique_sku("")

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
                0x06,
                0x00,
                0x00,
                0x00,
                0x1F,
                0x15,
                0xC4,
                0x89,
                0x00,
                0x00,
                0x00,
                0x0B,
                0x49,
                0x44,
                0x41,
                0x54,
                0x78,
                0x9C,
                0x62,
                0x00,
                0x00,
                0x00,
                0x02,
                0x00,
                0x01,
                0xE2,
                0x21,
                0xBC,
                0x33,
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
        self._setup_shopify_mocks()  # Set up Shopify API mocks

        self.env["ir.config_parameter"].set_param("shopify.last_import.product", "2000-01-01T00:00:00Z")

        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_products")
        self.importer = ProductImporter(self.env, self.sync_record)

        self.manufacturer = self.env["product.manufacturer"].search([("name", "=", "Test Manufacturer")])
        if not self.manufacturer:
            self.manufacturer = self.env["product.manufacturer"].create({"name": "Test Manufacturer"})

        self.part_type = self.env["product.type"].search([("name", "=", "Motors")])
        if not self.part_type:
            self.part_type = self.env["product.type"].create({"name": "Motors", "ebay_category_id": "123456"})

        self.condition = self.env["product.condition"].search([("code", "=", "new")])
        if not self.condition:
            self.condition = self.env["product.condition"].create({"name": "New", "code": "new"})

    def _import_products_with_mock_data(self, product_data_list: list[dict]) -> int:
        try:
            product_fields_list = [ProductFields(**data) for data in product_data_list]
        except Exception as e:
            self.fail(f"Failed to create ProductFields from fixture data: {e}")

        imported_count = 0
        for product_fields in product_fields_list:
            if self.importer._import_one(product_fields):
                imported_count += 1

        return imported_count

    def _get_imported_product(self) -> "odoo.model.product_product":
        product = self.env["product.product"].search([("shopify_product_id", "!=", False)])
        self.assertTrue(product)
        return product

    def _import_and_get_product(self, product_data: dict, expected_count: int = 1) -> "odoo.model.product_product":
        try:
            product_fields = ProductFields(**product_data)
        except Exception as e:
            self.fail(f"Failed to create ProductFields from fixture data: {e}")

        result = self.importer._import_one(product_fields)
        imported_count = 1 if result else 0

        self.assertEqual(imported_count, expected_count)

        product = self.env["product.product"].search([("shopify_product_id", "=", "123456789")])
        self.assertTrue(
            product,
            f"Product with shopify_product_id=123456789 not found. Found products: {self.env['product.product'].search([]).mapped('shopify_product_id')}",
        )
        return product

    def _import_product_and_verify(self, product_data: dict, sku: str) -> "odoo.model.product_product":
        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result)

        product = self.env["product.product"].search([("default_code", "=", sku), ("active", "in", [True, False])])
        self.assertTrue(product, f"Product with SKU {sku} not found")
        return product

    def test_import_basic_product(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            title="Test Motor",
            vendor="Test Manufacturer",
            product_type="Motors",
            variants=[
                create_shopify_product_variant(
                    sku=sku,
                    barcode="1234567890",
                    weight=2.5,
                    unit_cost="45.00",
                )
            ],
            media=[],  # Explicitly set no media to avoid image processing issues
        )

        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result, "_import_one should return True for new product")

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} should have been created")
        self.assertEqual(product.name, "Test Motor")
        self.assertEqual(product.list_price, 99.99)
        self.assertEqual(product.standard_price, 45.00)
        self.assertEqual(product.mpn, "1234567890")
        self.assertEqual(product.weight, 2.5)
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.is_storable)
        self.assertEqual(product.product_tmpl_id.manufacturer.name, "Test Manufacturer")

    def test_import_product_with_bin_location(self) -> None:
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(
                    sku=f"{self._get_unique_sku()} - A1-B2",
                )
            ],
        )

        product = self._import_and_get_product(product_data)
        self.assertEqual(product.bin, "A1-B2")

    def test_import_product_with_metafields(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            product_type="Motors",
            metafields=[
                create_shopify_metafield(key="condition", value="new"),
                create_shopify_metafield(key="ebay_category_id", value="123456"),
            ],
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        template = product.product_tmpl_id

        self.assertTrue(template.condition, "Product template should have a condition")
        self.assertEqual(template.condition.code, "new")
        self.assertTrue(template.part_type, "Product template should have a part type")
        self.assertEqual(template.part_type.name, "Motors")
        self.assertEqual(str(template.part_type.ebay_category_id), "123456")

    def test_import_product_with_images(self) -> None:
        encoded_image = self._get_valid_image_base64()
        sku = generate_unique_sku()

        product_data = create_shopify_product_response(
            media=[
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/111",
                    alt="Front view",
                    status=MediaStatus.READY,
                    url="https://example.com/image1.jpg",
                ),
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/222",
                    alt="Side view",
                    status=MediaStatus.READY,
                    url="https://example.com/image2.jpg",
                ),
            ],
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        with patch.object(self.importer, "fetch_image_data") as mock_fetch_image:
            mock_fetch_image.return_value = encoded_image

            product_fields = ProductFields(**product_data)
            result = self.importer._import_one(product_fields)

        self.assertTrue(result)

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} not found")
        self.assertEqual(len(product.images), 2)
        self.assertEqual(product.images[0].name, "Front view")
        self.assertEqual(product.images[0].shopify_media_id, "111")
        self.assertEqual(product.images[1].name, "Side view")
        self.assertEqual(product.images[1].shopify_media_id, "222")

    def test_import_product_with_processing_images(self) -> None:
        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/999",
            media=[
                create_shopify_product_image(status=MediaStatus.PROCESSING),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])
            imported_count = self.importer.import_products_since_last_import()

        self.assertEqual(imported_count, 0)

        reimport_sync = self.env["shopify.sync"].search(
            [
                ("mode", "=", "import_one_product"),
                ("shopify_product_id_to_sync", "=", "999"),
            ]
        )
        self.assertTrue(reimport_sync)

    def test_import_product_with_failed_images(self) -> None:
        existing_product = ProductFactory.create(
            self.env,
            name="Existing Product",
            default_code=self._get_unique_sku(),
            shopify_product_id="888",
        ).product_variant_id

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/888",
            variants=[
                create_shopify_product_variant(sku=existing_product.default_code),
            ],
            media=[
                create_shopify_product_image(status=MediaStatus.FAILED),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            self.importer.import_products_since_last_import()

        existing_product.invalidate_recordset()
        self.assertTrue(existing_product.shopify_next_export)

    def test_import_product_missing_sku(self) -> None:
        product_data = create_shopify_product_response(
            variants=[
                create_shopify_product_variant(sku=""),  # Empty SKU
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])
            imported_count = self.importer.import_products_since_last_import()

        self.assertEqual(imported_count, 0)

    def test_import_product_no_variants(self) -> None:
        product_data = create_shopify_product_response(variants=[])

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            with self.assertRaises(ShopifyDataError) as cm:
                self.importer.import_products_since_last_import()

            self.assertIn("No variants found", str(cm.exception))

    def test_update_existing_product(self) -> None:
        existing_product = ProductFactory.create(
            self.env,
            name="Old Name",
            default_code=self._get_unique_sku(),
            shopify_product_id="777",
            list_price=50.00,
        ).product_variant_id

        with patch(
            "odoo.addons.product_connect.services.shopify.sync.importers.product_importer.determine_latest_odoo_product_modification_time"
        ) as mock_date:
            mock_date.return_value = datetime(2023, 1, 1)

            product_data = create_shopify_product_response(
                gid="gid://shopify/Product/777",
                title="New Name",
                updated_at=datetime(2023, 12, 31).isoformat(),
                variants=[
                    create_shopify_product_variant(
                        sku=existing_product.default_code,
                        price="75.00",
                    ),
                ],
            )

            product_fields = ProductFields(**product_data)
            result = self.importer._import_one(product_fields)

            self.assertTrue(result)

            existing_product.invalidate_recordset()
            self.assertEqual(existing_product.name, "New Name")
            self.assertEqual(existing_product.list_price, 75.00)

    def test_skip_up_to_date_product(self) -> None:
        sku = generate_unique_sku()
        ProductFactory.create(
            self.env,
            name="Current Product",
            default_code=sku,
            shopify_product_id="666",
        )

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/666",
            updated_at=datetime(2020, 1, 1).isoformat(),
            media=[],  # Explicitly set empty media
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        with (
            patch.object(self.importer, "_fetch_page") as mock_fetch,
            patch(
                "odoo.addons.product_connect.services.shopify.sync.importers.product_importer.determine_latest_odoo_product_modification_time"
            ) as mock_date,
        ):
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])
            mock_date.return_value = datetime(2023, 1, 1)
            imported_count = self.importer.import_products_since_last_import()

        self.assertEqual(imported_count, 0)

    def test_import_product_with_inventory(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            total_inventory=25,
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result)

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} not found")

    def test_import_inactive_product(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            status=ProductStatus.DRAFT,
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        # Products from Shopify should always be active and published regardless of status
        self.assertTrue(product.active, "Products from Shopify should always be active")
        self.assertTrue(product.is_published, "Products from Shopify should always be published")

    def test_create_manufacturer_if_not_exists(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            vendor="New Manufacturer",
            media=[],  # No media to avoid image fetching issues
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result)

        manufacturer = self.env["product.manufacturer"].search([("name", "=", "New Manufacturer")])
        self.assertTrue(manufacturer)

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} not found")
        self.assertEqual(product.product_tmpl_id.manufacturer, manufacturer)

    def test_create_part_type_if_not_exists(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            product_type="New Part Type",
            media=[],  # No media to avoid image fetching issues
            metafields=[
                create_shopify_metafield(key="ebay_category_id", value="999999"),
            ],
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result)

        part_type = self.env["product.type"].search(
            [
                ("name", "=", "New Part Type"),
                ("ebay_category_id", "=", "999999"),
            ]
        )
        self.assertTrue(part_type)

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} not found")
        self.assertEqual(product.product_tmpl_id.part_type, part_type)

    def test_invalid_ebay_category_id(self) -> None:
        product_data = create_shopify_product_response(
            product_type="Motors",
            metafields=[
                create_shopify_metafield(key="ebay_category_id", value="invalid"),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            with self.assertRaises(ShopifyDataError) as cm:
                self.importer.import_products_since_last_import()

            self.assertIn("Invalid ebay_category_id", str(cm.exception))

    def test_fetch_image_data_error(self) -> None:
        product_data = create_shopify_product_response(
            media=[
                create_shopify_product_image(
                    status=MediaStatus.READY,
                    url="https://example.com/bad-image.jpg",
                ),
            ],
        )

        with (
            patch.object(self.importer, "_fetch_page") as mock_fetch,
            patch.object(self.mock_client.http_client, "stream") as mock_stream,
        ):
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            mock_stream.side_effect = Exception("Network error")

            with self.assertRaises(ShopifyDataError) as cm:
                self.importer.import_products_since_last_import()

            self.assertIn("Network error", str(cm.exception))

    def test_images_already_in_sync(self) -> None:
        sku = generate_unique_sku()
        existing_product = ProductFactory.create(
            self.env,
            name="Product with Images",
            default_code=sku,
            shopify_product_id="555",
        ).product_variant_id

        self.env["product.image"].create(
            {
                "name": "Image 1",
                "shopify_media_id": "111",
                "image_1920": self._get_valid_image_base64(),
                "product_tmpl_id": existing_product.product_tmpl_id.id,
            }
        )
        self.env["product.image"].create(
            {
                "name": "Image 2",
                "shopify_media_id": "222",
                "image_1920": self._get_valid_image_base64(),
                "product_tmpl_id": existing_product.product_tmpl_id.id,
            }
        )

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/555",
            updated_at=datetime(2023, 12, 31).isoformat(),
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
            media=[
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/111",
                    status=MediaStatus.READY,
                ),
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/222",
                    status=MediaStatus.READY,
                ),
            ],
        )

        with (
            patch(
                "odoo.addons.product_connect.services.shopify.sync.importers.product_importer.determine_latest_odoo_product_modification_time"
            ) as mock_date,
            patch.object(self.importer, "fetch_image_data") as mock_fetch_image,
        ):
            mock_date.return_value = datetime(2023, 1, 1)

            product_fields = ProductFields(**product_data)
            result = self.importer._import_one(product_fields)

            self.assertTrue(result)
            mock_fetch_image.assert_not_called()

    def test_product_with_zero_weight(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(sku=sku, weight=0),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        self.assertEqual(product.weight, 0.0)

    def test_product_data_error_handling(self) -> None:
        product_data = create_shopify_product_response(
            variants=[
                create_shopify_product_variant(
                    sku="",
                ),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])
            imported_count = self.importer.import_products_since_last_import()

        self.assertEqual(imported_count, 0)

    def test_import_product_with_extreme_prices(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(
                    sku=sku,
                    price="9999999.99",  # Very high price
                    unit_cost="0.01",  # Very low cost
                ),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        self.assertEqual(product.list_price, 9999999.99)
        self.assertEqual(product.standard_price, 0.01)

    def test_import_product_with_html_in_description(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            title="<b>Bold Product</b>",
            media=[],  # No media to avoid image processing issues,
            description='<script>alert("XSS")</script><p>Product <b>description</b> with <a href="https://example.com">links</a></p>',
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        self.assertIn("<p>Product", product.website_description)
        self.assertNotIn("<b>", product.name)

    def test_import_product_with_unicode_sku(self) -> None:
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(
                    sku=f"{self._get_unique_sku()} - BIN-01",
                ),
            ],
        )

        product = self._import_and_get_product(product_data)
        self.assertEqual(product.bin, "BIN-01")

    def test_import_product_with_very_long_sku_and_bin(self) -> None:
        base_sku = self._get_unique_sku()
        long_sku = base_sku + "1" * 40  # Total ~50 chars
        long_bin = "BIN-" + "B" * 45  # Total ~50 chars
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(
                    sku=f"{long_sku} - {long_bin}",
                ),
            ],
        )

        product_fields = ProductFields(**product_data)
        result = self.importer._import_one(product_fields)
        self.assertTrue(result, "Product import should succeed")

        products = self.env["product.product"].search(
            ["|", ("default_code", "like", base_sku + "%"), ("shopify_product_id", "=", "123456789")]
        )
        self.assertTrue(
            products,
            f"Product with SKU starting with {base_sku} or shopify_product_id=123456789 not found. All products: {self.env['product.product'].search([]).mapped('default_code')}",
        )
        product = products[0]
        self.assertTrue(product.default_code)
        self.assertTrue(product.bin)

    def test_import_product_with_conflicting_sku_and_id(self) -> None:
        ProductFactory.create(
            self.env,
            name="Product 1",
            default_code=self._get_unique_sku(),
            shopify_product_id="111",
        )

        product2 = ProductFactory.create(
            self.env,
            name="Product 2",
            default_code=self._get_unique_sku(),
            shopify_product_id="222",
        ).product_variant_id

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/222",
            title="Updated Product",
            variants=[
                create_shopify_product_variant(sku=product2.default_code),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            self.importer.import_products_since_last_import()

        product2.invalidate_recordset()
        self.assertEqual(product2.name, "Updated Product")
        self.assertTrue(product2.default_code)

    def test_import_product_with_invalid_metafield_types(self) -> None:
        product_data = create_shopify_product_response(
            product_type="Motors",
            metafields=[
                create_shopify_metafield(key="condition", value="INVALID_CONDITION"),
                create_shopify_metafield(key="ebay_category_id", value="not-a-number"),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            with self.assertRaises(ShopifyDataError):
                self.importer.import_products_since_last_import()

    def test_import_product_with_massive_image_count(self) -> None:
        sku = generate_unique_sku()
        images = []
        for i in range(50):
            images.append(
                create_shopify_product_image(
                    gid=f"gid://shopify/MediaImage/{i + 1000}",
                    alt=f"Image {i}",
                    status=MediaStatus.READY,
                    url=f"https://example.com/image{i}.jpg",
                )
            )

        product_data = create_shopify_product_response(
            media=images,
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        with patch.object(self.importer, "fetch_image_data") as mock_fetch_image:
            mock_fetch_image.return_value = self._get_valid_image_base64()

            product_fields = ProductFields(**product_data)
            result = self.importer._import_one(product_fields)

        self.assertTrue(result)

        product = self.env["product.product"].search([("default_code", "=", sku)])
        self.assertTrue(product, f"Product with SKU {sku} not found")
        self.assertEqual(len(product.images), 50)

    def test_import_product_with_network_retry(self) -> None:
        product_data = create_shopify_product_response(
            media=[
                create_shopify_product_image(status=MediaStatus.READY),
            ],
        )

        with (
            patch.object(self.importer, "_fetch_page") as mock_fetch,
            patch.object(self.mock_client.http_client, "stream") as mock_stream,
        ):
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            mock_stream.side_effect = [
                Exception("Connection reset"),
            ]

            with self.assertRaises(ShopifyDataError):
                self.importer.import_products_since_last_import()

    def test_import_product_inactive_then_active(self) -> None:
        sku = self._get_unique_sku()
        existing_template = ProductFactory.create(
            self.env,
            name="Inactive Product",
            default_code=sku,
            shopify_product_id="333",
            active=False,
            is_published=False,  # Initially not published
        )
        existing_product = existing_template.product_variant_id

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/333",
            status=ProductStatus.ACTIVE,
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
        )

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = create_mock_simple_response([ProductFields(**product_data)])

            self.importer.import_products_since_last_import()

        existing_template.invalidate_recordset()
        existing_product.invalidate_recordset()

        self.assertTrue(existing_template.active, "Product template should be activated")
        self.assertTrue(existing_template.is_published, "Product should be published after import")

    def test_import_product_with_null_inventory_fields(self) -> None:
        sku = generate_unique_sku()
        product_data = create_shopify_product_response(
            media=[],  # No media to avoid image processing issues
            variants=[
                create_shopify_product_variant(
                    sku=sku,
                    inventoryItem={
                        "unitCost": {"amount": "0", "currencyCode": "USD"},
                        "measurement": {"weight": {"value": 0, "unit": "KILOGRAMS"}},
                    },
                ),
            ],
        )

        product = self._import_product_and_verify(product_data, sku)
        self.assertEqual(product.standard_price, 0.0)
        self.assertEqual(product.weight, 0.0)

    def test_import_product_with_reordered_images(self) -> None:
        sku = generate_unique_sku()
        existing_product = ProductFactory.create(
            self.env,
            name="Product with Images",
            default_code=sku,
            shopify_product_id="444",
        ).product_variant_id

        self.env["product.image"].create(
            {
                "name": "Image 1",
                "shopify_media_id": "111",
                "image_1920": self._get_valid_image_base64(),
                "product_tmpl_id": existing_product.product_tmpl_id.id,
                "sequence": 0,
            }
        )
        self.env["product.image"].create(
            {
                "name": "Image 2",
                "shopify_media_id": "222",
                "image_1920": self._get_valid_image_base64(),
                "product_tmpl_id": existing_product.product_tmpl_id.id,
                "sequence": 1,
            }
        )

        product_data = create_shopify_product_response(
            gid="gid://shopify/Product/444",
            updated_at=datetime(2020, 1, 1).isoformat(),  # Old date
            variants=[
                create_shopify_product_variant(sku=sku),
            ],
            media=[
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/222",
                    status=MediaStatus.READY,
                    alt="Image 2 Updated",
                ),
                create_shopify_product_image(
                    gid="gid://shopify/MediaImage/111",
                    status=MediaStatus.READY,
                    alt="Image 1 Updated",
                ),
            ],
        )

        with patch.object(self.importer, "fetch_image_data") as mock_fetch_image:
            mock_fetch_image.return_value = self._get_valid_image_base64()

            product_fields = ProductFields(**product_data)
            result = self.importer._import_one(product_fields)

            self.assertTrue(result, "Import should detect image order change")

        existing_product.invalidate_recordset()
        images = sorted(existing_product.images, key=lambda x: x.sequence)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].shopify_media_id, "222")
        self.assertEqual(images[0].sequence, 0)
        self.assertEqual(images[1].shopify_media_id, "111")
        self.assertEqual(images[1].sequence, 1)
        self.assertEqual(images[0].name, "Image 2 Updated")
        self.assertEqual(images[1].name, "Image 1 Updated")
