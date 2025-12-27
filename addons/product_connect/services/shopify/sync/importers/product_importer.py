import base64
import logging
from tempfile import NamedTemporaryFile
from typing import Optional

from httpx import HTTPError
from odoo.api import Environment
from odoo.tools.mail import html2plaintext
from pydantic import AnyUrl

from ...gql import (
    Client,
    MediaStatus,
    GetProductsProducts,
    ProductFields,
    ProductFieldsMediaNodesMediaImage,
)
from ..base import ShopifyBaseImporter
from ...helpers import (
    SyncMode,
    ShopifyDataError,
    ShopifyMissingSkuFieldError,
    determine_latest_odoo_product_modification_time,
    image_order_key,
    parse_shopify_id_from_gid,
    parse_shopify_sku_field_to_sku_and_bin,
    write_if_changed,
)

_logger = logging.getLogger(__name__)


class ProductImporter(ShopifyBaseImporter[ProductFields]):
    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        super().__init__(env, sync_record)

    def _fetch_page(self, client: Client, query: str | None, cursor: str | None) -> GetProductsProducts:
        return client.get_products(query=query, cursor=cursor, limit=self.page_size)

    def import_products_since_last_import(self) -> int:
        return self.run_since_last_import("product")

    def _import_one(self, shopify_product: ProductFields) -> bool:
        if not shopify_product.variants or not shopify_product.variants.nodes:
            raise ShopifyDataError(f"No variants found", shopify_record=shopify_product)

        variant = shopify_product.variants.nodes[0]

        try:
            shopify_sku, _bin_location = parse_shopify_sku_field_to_sku_and_bin(variant.sku)
        except ShopifyMissingSkuFieldError:
            _logger.warning(f"Missing SKU for product {shopify_product.id} {shopify_product.title}")
            return False

        odoo_product = (
            self.env["product.product"]
            .search(
                [
                    "|",
                    ("shopify_product_id", "=", parse_shopify_id_from_gid(shopify_product.id)),
                    ("default_code", "=", shopify_sku),
                    ("active", "in", [True, False]),
                ],
                limit=1,
            )
            .with_context(skip_shopify_sync=True)
        )

        if self._has_processing_images(shopify_product, odoo_product):
            return False

        try:
            if odoo_product:
                latest_write_date = determine_latest_odoo_product_modification_time(odoo_product)
                images = shopify_product.media.nodes

                if any(image.status == MediaStatus.FAILED for image in images):
                    _logger.debug(f"Product {odoo_product.id} has media failed. Flagging for re‑import.")
                    odoo_product.shopify_next_export = True

                if shopify_product.updated_at > latest_write_date:
                    _logger.debug(f"Updating existing product {odoo_product.id} from Shopify")
                    odoo_product = self.save_odoo_product(odoo_product, shopify_product)
                    return True

                shopify_images = [image for image in shopify_product.media.nodes if image.status == MediaStatus.READY]
                if not self._images_are_in_sync(odoo_product, shopify_images):
                    _logger.debug(f"Product {odoo_product.id} has image order changes, updating from Shopify")
                    odoo_product = self.save_odoo_product(odoo_product, shopify_product)
                    return True

                _logger.debug(f"Product {odoo_product.id} is up to date with Shopify")
                return False
            else:
                _logger.debug(f"Creating new product {shopify_product.id} from Shopify")
                odoo_product = self.save_odoo_product(None, shopify_product)
                return True

        except ValueError as error:
            raise ShopifyDataError(
                f"Failed to update Odoo product",
                shopify_record=shopify_product,
                odoo_record=odoo_product,
            ) from error

    def _has_processing_images(self, shopify_product: ProductFields, odoo_product: Optional["odoo.model.product_product"]) -> bool:
        images = shopify_product.media.nodes
        if any(image.status in (MediaStatus.PROCESSING, MediaStatus.UPLOADED) for image in images):
            product_desc = f"Product {odoo_product.id}" if odoo_product else f"New product {shopify_product.id}"
            _logger.debug(f"{product_desc} has media not yet ready. Flagging for re-import.")
            self.env["shopify.sync"].create(
                {
                    "mode": SyncMode.IMPORT_ONE_PRODUCT,
                    "shopify_product_id_to_sync": parse_shopify_id_from_gid(shopify_product.id),
                }
            )
            return True
        return False

    def _images_are_in_sync(
        self, odoo_product: "odoo.model.product_product", shopify_images: list[ProductFieldsMediaNodesMediaImage]
    ) -> bool:
        template_images = odoo_product.product_tmpl_id.images
        if len(template_images) != len(shopify_images):
            _logger.debug(
                f"Image count mismatch for product {odoo_product.id}: Odoo has {len(template_images)}, Shopify has {len(shopify_images)}"
            )
            return False
        if any(image.shopify_media_id is None for image in template_images):
            _logger.debug(f"Missing Shopify media ID for product {odoo_product.id}")
            return False
        return self._ordered_odoo_media_ids(odoo_product) == self._ordered_shopify_media_ids(shopify_images)

    def get_or_create_manufacturer(self, manufacturer_name: str) -> "odoo.model.product_manufacturer":
        manufacturer = self.env["product.manufacturer"].search([("name", "=", manufacturer_name)], limit=1)
        if not manufacturer:
            manufacturer = self.env["product.manufacturer"].create({"name": manufacturer_name})
        return manufacturer

    def get_or_create_part_type(self, part_type_name: str, ebay_category_id: str) -> "odoo.model.product_type":
        if not ebay_category_id or not ebay_category_id.isdigit() or ebay_category_id == "0":
            raise ShopifyDataError(f"Invalid ebay_category_id {ebay_category_id}")

        if not part_type_name:
            raise ShopifyDataError(f"Invalid part_type_name {part_type_name}")
        part_type = self.env["product.type"].search(
            [
                ("name", "=", part_type_name),
                ("ebay_category_id", "=", ebay_category_id),
            ],
            limit=1,
        )
        if not part_type:
            part_type = self.env["product.type"].create({"name": part_type_name, "ebay_category_id": ebay_category_id})

        return part_type

    def import_images_from_shopify(self, odoo_product: "odoo.model.product_product", shopify_product: ProductFields) -> None:
        shopify_images = [image for image in shopify_product.media.nodes if image.status == MediaStatus.READY]
        if not shopify_images:
            _logger.debug(f"No images to import for product {shopify_product.id} {shopify_product.title}")
            return

        if self._images_are_in_sync(odoo_product, shopify_images):
            _logger.debug(f"Images already in sync for product {odoo_product.id}")
            return

        _logger.debug(f"Updating images for product {odoo_product.id} from Shopify")

        existing_by_mid = {image.shopify_media_id: image for image in odoo_product.product_tmpl_id.images if image.shopify_media_id}
        ordered_images = []

        for shopify_image in shopify_images:
            media_id = parse_shopify_id_from_gid(shopify_image.id)
            image = existing_by_mid.get(media_id)
            if image:
                if shopify_image.alt and image.name != shopify_image.alt:
                    image.name = shopify_image.alt
            else:
                preview_url = shopify_image.preview.image.url
                if not preview_url:
                    exception = ShopifyDataError(
                        "No image URL for product", shopify_record=shopify_product, odoo_record=odoo_product
                    )
                    _logger.error(exception)
                    raise exception
                image = self.env["product.image"].create(
                    {
                        "name": shopify_image.alt or shopify_product.title,
                        "image_1920": self.fetch_image_data(preview_url),
                        "shopify_media_id": media_id,
                    }
                )
            ordered_images.append(image)

        odoo_product.product_tmpl_id.images = [(6, 0, [image.id for image in ordered_images])]

        for sequence, image in enumerate(ordered_images):
            image.with_context(skip_shopify_sync=True).sequence = sequence

    def fetch_image_data(self, image_url: AnyUrl) -> str:
        client = self.service.client.http_client
        try:
            with client.stream("GET", str(image_url), follow_redirects=True) as response:
                response.raise_for_status()
                with NamedTemporaryFile() as temp_file:
                    for chunk in response.iter_bytes():
                        temp_file.write(chunk)
                    temp_file.seek(0)

                    return base64.b64encode(temp_file.read()).decode()
        except HTTPError as error:
            exception = ShopifyDataError(f"Failed to fetch image data from {image_url}")
            _logger.error(exception)
            raise exception from error

    @staticmethod
    def _ordered_odoo_media_ids(product: "odoo.model.product_product") -> list[str]:
        ordered_images = sorted(product.product_tmpl_id.images, key=image_order_key)
        return [image.shopify_media_id for image in ordered_images if image.shopify_media_id]

    @staticmethod
    def _ordered_shopify_media_ids(shopify_images: list[ProductFieldsMediaNodesMediaImage]) -> list[str]:
        return [parse_shopify_id_from_gid(image.id) for image in shopify_images]

    def _sync_images_bidirectional(self, odoo_product: "odoo.model.product_product", shopify_product: ProductFields) -> None:
        self.import_images_from_shopify(odoo_product, shopify_product)

    def save_odoo_product(
        self, odoo_product: Optional["odoo.model.product_product"], shopify_product: ProductFields
    ) -> "odoo.model.product_product":
        try:
            variant = shopify_product.variants.nodes[0]
            sku, bin_location = parse_shopify_sku_field_to_sku_and_bin(variant.sku or "")
            metafields = shopify_product.metafields.nodes
            metafields_by_key = {mf.key: mf for mf in metafields}

            odoo_product_input: "odoo.values.product_product" = {
                "shopify_product_id": parse_shopify_id_from_gid(shopify_product.id),
                "shopify_variant_id": parse_shopify_id_from_gid(variant.id),
                "shopify_created_at": shopify_product.created_at,
                "name": html2plaintext(shopify_product.title).strip() if shopify_product.title else "",
                "default_code": sku,
                "website_description": shopify_product.description_html,
                "list_price": float(variant.price),
                "standard_price": float(variant.inventory_item.unit_cost.amount or 0 if variant.inventory_item.unit_cost else 0),
                "mpn": variant.barcode,
                "bin": bin_location,
                "weight": variant.inventory_item.measurement.weight.value if variant.inventory_item.measurement.weight else 0,
                "type": "consu",
                "is_storable": True,
                "manufacturer": self.get_or_create_manufacturer(shopify_product.vendor).id if shopify_product.vendor else False,
                "is_published": True,  # Always true for products imported from Shopify
                "is_ready_for_sale": True,
                "active": True,
            }

            template_vals = {"active": True}

            condition_metafield = metafields_by_key.get("condition")
            if condition_metafield:
                condition = self.env["product.condition"].search([("code", "=", condition_metafield.value)], limit=1)
                if condition:
                    template_vals["condition"] = condition.id

            ebay_category_from_shopify = metafields_by_key.get("ebay_category_id")
            if ebay_category_from_shopify:
                odoo_product_input["shopify_ebay_category_id"] = parse_shopify_id_from_gid(ebay_category_from_shopify.id)
                template_vals["part_type"] = self.get_or_create_part_type(
                    shopify_product.product_type, ebay_category_from_shopify.value
                ).id

            if odoo_product:
                write_if_changed(odoo_product, odoo_product_input)
                if template_vals:
                    write_if_changed(odoo_product.product_tmpl_id, template_vals)
            else:
                odoo_product_input["source"] = "shopify"
                odoo_product = (
                    self.env["product.product"].with_context(skip_shopify_sync=True, force_sku_check=True).create(odoo_product_input)
                )
                if template_vals:
                    write_if_changed(odoo_product.product_tmpl_id, template_vals)

            self._sync_images_bidirectional(odoo_product, shopify_product)
            if shopify_product.total_inventory is not None:
                stock_availability_changed = bool(odoo_product.qty_available) != bool(shopify_product.total_inventory)
                if stock_availability_changed:
                    odoo_product.shopify_next_export = True

                odoo_product.update_quantity(shopify_product.total_inventory)

            return odoo_product

        except (ValueError, TypeError, AttributeError) as error:
            exception = ShopifyDataError("Failed to save Odoo product", shopify_record=shopify_product, odoo_record=odoo_product)
            _logger.error(exception)
            raise exception from error
