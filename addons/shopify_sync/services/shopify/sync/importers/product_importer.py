import base64
import logging
from dataclasses import dataclass
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
from ..change_detection import changed_values, write_if_changed
from ...helpers import (
    SyncMode,
    ShopifyDataError,
    ShopifyMissingSkuFieldError,
    find_record_by_external_id,
    image_order_key,
    parse_shopify_id_from_gid,
    parse_shopify_sku_field_to_sku_and_bin,
    upsert_external_id,
)

_logger = logging.getLogger(__name__)


@dataclass
class ProductSyncValues:
    product_values: "odoo.values.product_product"
    template_values: "odoo.values.product_template"


@dataclass
class ExistingProductEvaluation:
    sync_values: ProductSyncValues
    linked_missing_external_ids: bool
    has_failed_images: bool
    manufacturer_changed: bool
    part_type_changed: bool
    quantity_changed: bool
    images_in_sync: bool
    product_changes: dict
    template_changes: dict

    @property
    def requires_related_record_resolution(self) -> bool:
        return self.manufacturer_changed or self.part_type_changed

    @property
    def should_update(self) -> bool:
        return bool(
            self.product_changes
            or self.template_changes
            or self.requires_related_record_resolution
            or self.quantity_changed
            or not self.images_in_sync
        )


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

        odoo_product = self._find_matching_odoo_product(shopify_product, shopify_sku)

        if self._has_processing_images(shopify_product, odoo_product):
            return False

        try:
            if odoo_product:
                evaluation = self._evaluate_existing_product(odoo_product, shopify_product)

                if evaluation.has_failed_images:
                    _logger.debug(f"Product {odoo_product.id} has media failed. Flagging for re‑import.")
                    odoo_product.shopify_next_export = True

                if evaluation.should_update:
                    _logger.debug(f"Updating existing product {odoo_product.id} from Shopify")
                    odoo_product = self.save_odoo_product(
                        odoo_product,
                        shopify_product,
                        sync_values=None if evaluation.requires_related_record_resolution else evaluation.sync_values,
                    )
                    return True

                _logger.debug(f"Product {odoo_product.id} is up to date with Shopify")
                return evaluation.linked_missing_external_ids or evaluation.has_failed_images
            else:
                _logger.debug(f"Creating new product {shopify_product.id} from Shopify")
                odoo_product = self.save_odoo_product(None, shopify_product)
                return True

        except ValueError as error:
            raise ShopifyDataError(
                "Failed to update Odoo product",
                shopify_record=shopify_product,
                odoo_record=odoo_product,
            ) from error

    def _find_matching_odoo_product(
        self,
        shopify_product: ProductFields,
        shopify_sku: str,
    ) -> "odoo.model.product_product":
        product_model: "odoo.model.product_product" = self.env["product.product"].with_context(skip_shopify_sync=True)
        shopify_product_id = parse_shopify_id_from_gid(shopify_product.id)
        product_match = find_record_by_external_id(
            self.env,
            model_name="product.product",
            system_code="shopify",
            resource="product",
            external_id_value=shopify_product_id,
        )
        if product_match:
            return product_model.browse(product_match.id)

        variant = shopify_product.variants.nodes[0]
        shopify_variant_id = parse_shopify_id_from_gid(variant.id)
        variant_match = find_record_by_external_id(
            self.env,
            model_name="product.product",
            system_code="shopify",
            resource="variant",
            external_id_value=shopify_variant_id,
        )
        if variant_match:
            return product_model.browse(variant_match.id)

        return product_model.search(
            [
                ("default_code", "=", shopify_sku),
                ("active", "in", [True, False]),
            ],
            limit=1,
        )

    def _evaluate_existing_product(
        self,
        odoo_product: "odoo.model.product_product",
        shopify_product: ProductFields,
    ) -> ExistingProductEvaluation:
        sync_values = self._build_odoo_product_values(shopify_product)
        shopify_images = [image for image in shopify_product.media.nodes if image.status == MediaStatus.READY]
        return ExistingProductEvaluation(
            sync_values=sync_values,
            linked_missing_external_ids=self._link_missing_external_ids(odoo_product, shopify_product),
            has_failed_images=any(image.status == MediaStatus.FAILED for image in shopify_product.media.nodes),
            manufacturer_changed=self._manufacturer_change_detected(odoo_product, shopify_product),
            part_type_changed=self._part_type_change_detected(odoo_product, shopify_product),
            quantity_changed=(
                shopify_product.total_inventory is not None and shopify_product.total_inventory != odoo_product.qty_available
            ),
            images_in_sync=self._images_are_in_sync(odoo_product, shopify_images),
            product_changes=changed_values(
                odoo_product.with_context(skip_sku_check=True),
                sync_values.product_values,
            ),
            template_changes=changed_values(
                odoo_product.product_tmpl_id.with_context(skip_sku_check=True),
                sync_values.template_values,
            ),
        )

    @staticmethod
    def _link_missing_external_ids(
        odoo_product: "odoo.model.product_product",
        shopify_product: ProductFields,
    ) -> bool:
        variant = shopify_product.variants.nodes[0]
        metafields_by_key = {metafield.key: metafield for metafield in shopify_product.metafields.nodes}
        condition_metafield = metafields_by_key.get("condition")
        ebay_category_metafield = metafields_by_key.get("ebay_category_id")

        desired_external_ids = {
            "product": parse_shopify_id_from_gid(shopify_product.id),
            "variant": parse_shopify_id_from_gid(variant.id),
            "condition": parse_shopify_id_from_gid(condition_metafield.id) if condition_metafield else None,
            "ebay_category": parse_shopify_id_from_gid(ebay_category_metafield.id) if ebay_category_metafield else None,
        }
        linked_missing_external_ids = False
        for resource, external_id_value in desired_external_ids.items():
            if not external_id_value:
                continue
            if (odoo_product.get_external_system_id("shopify", resource) or None) == external_id_value:
                continue
            upsert_external_id(
                odoo_product,
                system_code="shopify",
                resource=resource,
                external_id_value=external_id_value,
            )
            linked_missing_external_ids = True
        return linked_missing_external_ids

    @staticmethod
    def _upsert_optional_external_id(
        odoo_product: "odoo.model.product_product",
        *,
        resource: str,
        external_id_value: str | None,
    ) -> None:
        if not external_id_value:
            return
        upsert_external_id(
            odoo_product,
            system_code="shopify",
            resource=resource,
            external_id_value=external_id_value,
        )

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

    @staticmethod
    def _template_images(
        template: "odoo.model.product_template",
    ) -> "odoo.model.product_image":
        if hasattr(template, "product_template_image_ids"):
            return template.product_template_image_ids
        if hasattr(template, "images"):
            return template.images
        return template.env["product.image"]

    @staticmethod
    def _assign_template_images(
        template: "odoo.model.product_template", ordered_images: list["odoo.model.product_image"]
    ) -> None:
        image_ids = [image.id for image in ordered_images]
        if hasattr(template, "product_template_image_ids"):
            template.product_template_image_ids = [(6, 0, image_ids)]
        elif hasattr(template, "images"):
            template.images = [(6, 0, image_ids)]

    def _images_are_in_sync(
        self, odoo_product: "odoo.model.product_product", shopify_images: list[ProductFieldsMediaNodesMediaImage]
    ) -> bool:
        template_images = self._template_images(odoo_product.product_tmpl_id)
        if len(template_images) != len(shopify_images):
            _logger.debug(
                f"Image count mismatch for product {odoo_product.id}: Odoo has {len(template_images)}, Shopify has {len(shopify_images)}"
            )
            return False
        if any(not image.get_external_system_id("shopify", "media") for image in template_images):
            _logger.debug(f"Missing Shopify media ID for product {odoo_product.id}")
            return False
        return self._ordered_odoo_media_ids(odoo_product) == self._ordered_shopify_media_ids(shopify_images)

    def get_or_create_manufacturer(self, manufacturer_name: str) -> "odoo.model.product_manufacturer":
        manufacturer = self.env["product.manufacturer"].search([("name", "=", manufacturer_name)], limit=1)
        if not manufacturer:
            manufacturer = self.env["product.manufacturer"].create({"name": manufacturer_name})
        return manufacturer

    def _get_manufacturer(self, manufacturer_name: str) -> "odoo.model.product_manufacturer":
        return self.env["product.manufacturer"].search([("name", "=", manufacturer_name)], limit=1)

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

    def _get_part_type(self, part_type_name: str, ebay_category_id: str) -> "odoo.model.product_type":
        if not ebay_category_id or not ebay_category_id.isdigit() or ebay_category_id == "0" or not part_type_name:
            return self.env["product.type"].browse()

        return self.env["product.type"].search(
            [
                ("name", "=", part_type_name),
                ("ebay_category_id", "=", ebay_category_id),
            ],
            limit=1,
        )

    @staticmethod
    def _manufacturer_change_detected(
        odoo_product: "odoo.model.product_product",
        shopify_product: ProductFields,
    ) -> bool:
        template = odoo_product.product_tmpl_id
        incoming_vendor = shopify_product.vendor or ""
        if not incoming_vendor:
            return False

        current_manufacturer = template.manufacturer
        if not current_manufacturer:
            return True
        return current_manufacturer.name != incoming_vendor

    def _part_type_change_detected(self, odoo_product: "odoo.model.product_product", shopify_product: ProductFields) -> bool:
        metafields_by_key = {metafield.key: metafield for metafield in shopify_product.metafields.nodes}
        ebay_category_metafield = metafields_by_key.get("ebay_category_id")

        if not ebay_category_metafield:
            return False

        ebay_category_id = ebay_category_metafield.value
        if not ebay_category_id or not ebay_category_id.isdigit() or ebay_category_id == "0":
            return False

        incoming_part_type_name = shopify_product.product_type or ""
        if not incoming_part_type_name:
            return False

        current_part_type = odoo_product.product_tmpl_id.part_type
        matched_part_type = self._get_part_type(incoming_part_type_name, ebay_category_id)
        if not matched_part_type:
            if not current_part_type:
                return True
            if str(current_part_type.ebay_category_id) != ebay_category_id:
                return True
            return current_part_type.name != incoming_part_type_name

        return current_part_type != matched_part_type

    def import_images_from_shopify(self, odoo_product: "odoo.model.product_product", shopify_product: ProductFields) -> None:
        shopify_images = [image for image in shopify_product.media.nodes if image.status == MediaStatus.READY]
        if not shopify_images:
            _logger.debug(f"No images to import for product {shopify_product.id} {shopify_product.title}")
            return

        if self._images_are_in_sync(odoo_product, shopify_images):
            _logger.debug(f"Images already in sync for product {odoo_product.id}")
            return

        _logger.debug(f"Updating images for product {odoo_product.id} from Shopify")

        existing_by_mid: dict[str, "odoo.model.product_image"] = {}
        template_images = self._template_images(odoo_product.product_tmpl_id)
        for image in template_images:
            media_id = image.get_external_system_id("shopify", "media")
            if media_id:
                existing_by_mid[media_id] = image
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
                        "No image URL for product",
                        shopify_record=shopify_product,
                        odoo_record=odoo_product,
                    )
                    _logger.error(exception)
                    raise exception
                image = self.env["product.image"].create(
                    {
                        "name": shopify_image.alt or shopify_product.title,
                        "image_1920": self.fetch_image_data(preview_url),
                    }
                )
            upsert_external_id(image, system_code="shopify", resource="media", external_id_value=media_id)
            ordered_images.append(image)

        self._assign_template_images(odoo_product.product_tmpl_id, ordered_images)

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
        ordered_images = ProductImporter._template_images(product.product_tmpl_id).sorted(key=image_order_key)
        external_ids: list[str] = []
        for image in ordered_images:
            external_id = image.get_external_system_id("shopify", "media")
            if external_id:
                external_ids.append(external_id)
        return external_ids

    @staticmethod
    def _ordered_shopify_media_ids(shopify_images: list[ProductFieldsMediaNodesMediaImage]) -> list[str]:
        return [parse_shopify_id_from_gid(image.id) for image in shopify_images]

    def _sync_images_bidirectional(self, odoo_product: "odoo.model.product_product", shopify_product: ProductFields) -> None:
        self.import_images_from_shopify(odoo_product, shopify_product)

    def _build_odoo_product_values(
        self,
        shopify_product: ProductFields,
        *,
        create_related_records: bool = False,
    ) -> ProductSyncValues:
        variant = shopify_product.variants.nodes[0]
        sku, bin_location = parse_shopify_sku_field_to_sku_and_bin(variant.sku or "")
        metafields_by_key = {metafield.key: metafield for metafield in shopify_product.metafields.nodes}

        if shopify_product.vendor:
            if create_related_records:
                manufacturer = self.get_or_create_manufacturer(shopify_product.vendor)
            else:
                manufacturer = self._get_manufacturer(shopify_product.vendor)
        else:
            manufacturer = False

        odoo_product_input: "odoo.values.product_product" = {
            "shopify_created_at": shopify_product.created_at,
            "name": html2plaintext(shopify_product.title).strip() if shopify_product.title else "",
            "default_code": sku,
            "website_description": shopify_product.description_html,
            "list_price": float(variant.price),
            "standard_price": float(variant.inventory_item.unit_cost.amount or 0 if variant.inventory_item.unit_cost else 0),
            "mpn": variant.barcode,
            "weight": variant.inventory_item.measurement.weight.value if variant.inventory_item.measurement.weight else 0,
        }
        if manufacturer:
            odoo_product_input["manufacturer"] = manufacturer.id

        template_vals: "odoo.values.product_template" = {}
        template_model = self.env["product.template"]
        if "bin" in template_model._fields:
            template_vals["bin"] = bin_location

        condition_metafield = metafields_by_key.get("condition")
        if condition_metafield:
            condition = self.env["product.condition"].search([("code", "=", condition_metafield.value)], limit=1)
            if condition:
                template_vals["condition"] = condition.id

        ebay_category_from_shopify = metafields_by_key.get("ebay_category_id")
        if ebay_category_from_shopify:
            part_type = self._get_part_type(shopify_product.product_type, ebay_category_from_shopify.value)
            if create_related_records and not part_type and shopify_product.product_type:
                part_type = self.get_or_create_part_type(shopify_product.product_type, ebay_category_from_shopify.value)

            if part_type:
                template_vals["part_type"] = part_type.id

        return ProductSyncValues(
            product_values=odoo_product_input,
            template_values=template_vals,
        )

    def _apply_sync_defaults(
        self,
        sync_values: ProductSyncValues,
    ) -> ProductSyncValues:
        odoo_product_input = sync_values.product_values.copy()
        template_vals = sync_values.template_values.copy()

        odoo_product_input["type"] = "consu"
        odoo_product_input["is_storable"] = True
        odoo_product_input["is_published"] = True
        odoo_product_input["active"] = True

        template_vals["active"] = True
        template_model = self.env["product.template"]
        if "is_ready_for_sale" in template_model._fields:
            template_vals["is_ready_for_sale"] = True
        if "source" in template_model._fields:
            template_vals["source"] = "shopify"
            odoo_product_input["source"] = "shopify"

        return ProductSyncValues(
            product_values=odoo_product_input,
            template_values=template_vals,
        )

    def save_odoo_product(
        self,
        odoo_product: Optional["odoo.model.product_product"],
        shopify_product: ProductFields,
        *,
        sync_values: ProductSyncValues | None = None,
    ) -> "odoo.model.product_product":
        try:
            variant = shopify_product.variants.nodes[0]
            metafields = shopify_product.metafields.nodes
            metafields_by_key = {mf.key: mf for mf in metafields}
            shopify_product_id = parse_shopify_id_from_gid(shopify_product.id)
            shopify_variant_id = parse_shopify_id_from_gid(variant.id)

            if sync_values is None:
                sync_values = self._build_odoo_product_values(
                    shopify_product,
                    create_related_records=True,
                )
            sync_values = self._apply_sync_defaults(sync_values)
            odoo_product_input = sync_values.product_values
            template_vals = sync_values.template_values

            condition_metafield = metafields_by_key.get("condition")
            ebay_category_from_shopify = metafields_by_key.get("ebay_category_id")

            if odoo_product:
                write_if_changed(odoo_product.with_context(skip_sku_check=True), odoo_product_input)
                if template_vals:
                    write_if_changed(odoo_product.product_tmpl_id.with_context(skip_sku_check=True), template_vals)
            else:
                odoo_product = (
                    self.env["product.product"].with_context(skip_shopify_sync=True, skip_sku_check=True).create(odoo_product_input)
                )
                if template_vals:
                    write_if_changed(odoo_product.product_tmpl_id.with_context(skip_sku_check=True), template_vals)

            upsert_external_id(odoo_product, system_code="shopify", resource="product", external_id_value=shopify_product_id)
            upsert_external_id(odoo_product, system_code="shopify", resource="variant", external_id_value=shopify_variant_id)
            condition_external_id = (
                parse_shopify_id_from_gid(condition_metafield.id)
                if condition_metafield and getattr(condition_metafield, "id", None)
                else None
            )
            self._upsert_optional_external_id(
                odoo_product,
                resource="condition",
                external_id_value=condition_external_id,
            )
            ebay_category_external_id = (
                parse_shopify_id_from_gid(ebay_category_from_shopify.id)
                if ebay_category_from_shopify and getattr(ebay_category_from_shopify, "id", None)
                else None
            )
            self._upsert_optional_external_id(
                odoo_product,
                resource="ebay_category",
                external_id_value=ebay_category_external_id,
            )

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
