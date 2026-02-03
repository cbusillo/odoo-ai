import logging
from datetime import datetime
from decimal import Decimal

from odoo import fields
from odoo.api import Environment

from ...gql import (
    InventoryItemMeasurementInput,
    ProductSetProductSetProduct,
    ProductSetProductSetProductResourcePublicationsV2NodesPublication,
    ProductSetProductSetProductResourcePublicationsV2Nodes,
    GraphQLClientGraphQLMultiError,
    MediaStatus,
    MoveInput,
)
from ...gql.enums import FileContentType, ProductStatus, WeightUnit, LocalizableContentType
from ...gql.input_types import (
    ProductSetInput,
    ProductVariantSetInput,
    ProductSetInventoryInput,
    FileSetInput,
    PublicationInput,
    WeightInput,
    InventoryItemInput,
    MetafieldInput,
    OptionValueSetInput,
    OptionSetInput,
    VariantOptionValueInput,
    ProductSetIdentifiers,
)
from ...helpers import (
    PUBLICATION_CHANNELS,
    ShopifyApiError,
    format_shopify_gid_from_id,
    format_sku_bin_for_shopify,
    get_latest_image_write_date,
    image_order_key,
    parse_shopify_id_from_gid,
    upsert_external_id,
    write_if_changed,
)
from ..base import ShopifyBaseExporter

_logger = logging.getLogger(__name__)


class ProductExporter(ShopifyBaseExporter["odoo.model.product_product"]):
    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        super().__init__(env, sync_record)
        self.odoo_base_url = env["ir.config_parameter"].sudo().get_param("web.base.url")

    def export_products_since_last_export(self) -> None:
        _logger.info("Exporting products since last export")
        odoo_products = self._find_products_to_export()
        if not odoo_products:
            _logger.info("No products to export")
            return
        self.export_products(odoo_products)

    def export_products_since_datetime(self, cutoff_date: datetime) -> None:
        _logger.info(f"Exporting products since {cutoff_date}")
        odoo_products = self._find_products_to_export(cutoff_date)
        if not odoo_products:
            _logger.info("No products to export")
            return
        self.export_products(odoo_products)

    def _find_products_to_export(self, cutoff_date: datetime | None = None) -> "odoo.model.product_product":
        odoo_products = self.env["product.product"].search(
            [
                ("sale_ok", "=", True),
                ("is_ready_for_sale", "=", True),
                ("is_published", "=", True),
                ("website_description", "!=", False),
                ("website_description", "!=", ""),
                ("type", "=", "consu"),
            ]
        )
        if cutoff_date:
            odoo_products = odoo_products.filtered(
                lambda p: p.shopify_next_export is True or (p.write_date > cutoff_date or p.product_tmpl_id.write_date > cutoff_date)
            )

        else:
            odoo_products = odoo_products.filtered(
                lambda p: p.shopify_next_export is True
                or (
                    p.write_date > (p.shopify_last_exported_at or datetime.min)
                    or p.product_tmpl_id.write_date > (p.shopify_last_exported_at or datetime.min)
                )
            )
        return odoo_products

    def export_products(self, odoo_products: "odoo.model.product_product") -> None:
        self.run(odoo_products)

    def _export_one(self, odoo_product: "odoo.model.product_product") -> None:
        client = self.service.client

        shopify_product_id = odoo_product.get_external_system_id("shopify", "product")

        image_records = odoo_product.images
        latest_image_date = get_latest_image_write_date(odoo_product)
        images_need_update = latest_image_date > (odoo_product.shopify_last_exported_at or datetime.min)
        all_images_have_media_id = (
            all(image.get_external_system_id("shopify", "media") for image in image_records) if image_records else False
        )

        _logger.info(
            f"Exporting product {odoo_product.id} - images need update: {images_need_update}, "
            f"all have media IDs: {all_images_have_media_id}"
        )

        if (
            images_need_update
            and all_images_have_media_id
            and shopify_product_id
            and not odoo_product.shopify_next_export
        ):
            ordered_odoo_images = image_records.sorted(key=image_order_key)
            shopify_product_gid = format_shopify_gid_from_id("Product", shopify_product_id)
            if not self._verify_shopify_media_for_reorder(
                odoo_product,
                shopify_product_id,
                ordered_odoo_images,
            ):
                return
            self._reorder_shopify_media(odoo_product, shopify_product_gid, ordered_odoo_images)
            odoo_product.shopify_last_exported_at = fields.Datetime.now()
            return

        force_media_upload = bool(image_records) and not all_images_have_media_id
        shopify_product_set_input = self._map_odoo_product_to_shopify_product_set_input(
            odoo_product,
            images_need_update,
            force_media_upload=force_media_upload,
        )

        shopify_product_gid = (
            format_shopify_gid_from_id("Product", shopify_product_id) if shopify_product_id else None
        )
        if shopify_product_gid:
            identifier = ProductSetIdentifiers(id=shopify_product_gid)
        else:
            identifier = None

        try:
            shopify_response = client.product_set(shopify_product_set_input, identifier)
        except (ValueError, GraphQLClientGraphQLMultiError) as error:
            exception = ShopifyApiError("Error exporting product", odoo_record=odoo_product, shopify_input=shopify_product_set_input)
            _logger.error(exception)
            raise exception from error

        shopify_product = shopify_response.product
        if not shopify_product:
            exception = ShopifyApiError(
                "Shopify product not found in the response",
                shopify_record=shopify_response,
                odoo_record=odoo_product,
                shopify_input=shopify_product_set_input,
            )
            _logger.error(exception)
            raise exception

        publication_channels = shopify_product.resource_publications_v_2.nodes
        if not publication_channels or not self.is_published_on_all_channels(publication_channels):
            self._publish_product(shopify_product_gid or shopify_product.id)
        self._update_odoo_product(odoo_product, shopify_product)
        self._sync_images_after_export(odoo_product, shopify_product)

    @staticmethod
    def _update_odoo_product(odoo_product: "odoo.model.product_product", shopify_product: ProductSetProductSetProduct) -> None:
        metafields = shopify_product.metafields.nodes
        metafields_by_key = {metafield.key: metafield for metafield in metafields}
        ebay_category_id_metafield = metafields_by_key.get("ebay_category_id")
        condition_metafield = metafields_by_key.get("condition")
        _logger.debug(
            f"Updating product {odoo_product.id} with Shopify product {shopify_product.id} and metafields {metafields_by_key}"
        )

        shopify_product_id = parse_shopify_id_from_gid(shopify_product.id)
        shopify_variant_id = parse_shopify_id_from_gid(shopify_product.variants.nodes[0].id)
        condition_id = parse_shopify_id_from_gid(condition_metafield.id) if condition_metafield else None
        ebay_category_id = parse_shopify_id_from_gid(ebay_category_id_metafield.id) if ebay_category_id_metafield else None
        flags: "odoo.values.product_product" = {
            "shopify_next_export": False,
            "shopify_next_export_quantity_change_amount": 0,
        }
        write_if_changed(odoo_product, flags)
        upsert_external_id(odoo_product, system_code="shopify", resource="product", external_id_value=shopify_product_id)
        upsert_external_id(odoo_product, system_code="shopify", resource="variant", external_id_value=shopify_variant_id)
        upsert_external_id(odoo_product, system_code="shopify", resource="condition", external_id_value=condition_id)
        upsert_external_id(odoo_product, system_code="shopify", resource="ebay_category", external_id_value=ebay_category_id)
        odoo_product.shopify_last_exported_at = fields.Datetime.now()

    @staticmethod
    def _sync_images_after_export(odoo_product: "odoo.model.product_product", shopify_product: ProductSetProductSetProduct) -> None:
        shopify_media_nodes = shopify_product.media.nodes
        ordered_odoo_images = odoo_product.images.sorted(key=image_order_key)
        local_media_identifiers = {
            image.get_external_system_id("shopify", "media")
            for image in ordered_odoo_images
            if image.get_external_system_id("shopify", "media")
        }
        shopify_image_nodes = [
            node
            for node in shopify_media_nodes
            if getattr(node, "typename__", None) == "MediaImage"
        ]
        if not shopify_image_nodes:
            if local_media_identifiers:
                ProductExporter._clear_shopify_media_ids(ordered_odoo_images, local_media_identifiers)
                _logger.info(
                    "Shopify media missing for product %s after export. Scheduling re-export.",
                    odoo_product.id,
                )
                odoo_product.shopify_next_export = True
            return

        remote_media_identifiers = {
            parse_shopify_id_from_gid(node.id)
            for node in shopify_image_nodes
        }
        failed_media_identifiers = {
            parse_shopify_id_from_gid(node.id)
            for node in shopify_image_nodes
            if node.status == MediaStatus.FAILED
        }
        missing_media_identifiers = local_media_identifiers - remote_media_identifiers
        if failed_media_identifiers or missing_media_identifiers:
            ProductExporter._clear_shopify_media_ids(
                ordered_odoo_images,
                failed_media_identifiers | missing_media_identifiers,
            )
            _logger.info(
                "Shopify media missing/failed for product %s after export. Scheduling re-export.",
                odoo_product.id,
            )
            odoo_product.shopify_next_export = True
            return

        shopify_images = [image for image in shopify_image_nodes if image.status != MediaStatus.FAILED]
        if not shopify_images:
            return

        if len(ordered_odoo_images) != len(shopify_images):
            _logger.info(
                f"Mismatch immediately after export ({len(ordered_odoo_images)} Odoo vs {len(shopify_images)} Shopify). Scheduling retry."
            )
            odoo_product.shopify_next_export = True
            return

        for odoo_image, shopify_image in zip(ordered_odoo_images, shopify_images):
            media_id = parse_shopify_id_from_gid(shopify_image.id)
            if not odoo_image.get_external_system_id("shopify", "media"):
                upsert_external_id(odoo_image, system_code="shopify", resource="media", external_id_value=media_id)

            if shopify_image.alt and odoo_image.name != shopify_image.alt:
                odoo_image.name = shopify_image.alt

    def _verify_shopify_media_for_reorder(
        self,
        odoo_product: "odoo.model.product_product",
        shopify_product_id: str,
        ordered_odoo_images: "odoo.model.product_image",
    ) -> bool:
        client = self.service.client
        query = f'id:"{shopify_product_id}"'
        try:
            page = client.get_products(limit=1, query=query)
        except Exception as error:
            _logger.warning(
                "Unable to verify Shopify media for product %s before reorder: %s",
                odoo_product.id,
                error,
            )
            return True

        if not page.nodes:
            _logger.warning(
                "Shopify product %s missing during reorder verification. Scheduling re-export.",
                shopify_product_id,
            )
            self._schedule_media_reupload(odoo_product, ordered_odoo_images, reason="missing remote product")
            return False

        shopify_product = page.nodes[0]
        shopify_media_nodes = shopify_product.media.nodes
        shopify_image_nodes = [
            node
            for node in shopify_media_nodes
            if getattr(node, "typename__", None) == "MediaImage"
        ]
        if not shopify_image_nodes:
            _logger.warning(
                "Shopify product %s has no media during reorder verification. Scheduling re-export.",
                shopify_product_id,
            )
            self._schedule_media_reupload(odoo_product, ordered_odoo_images, reason="missing remote media")
            return False

        remote_media_identifiers = {
            parse_shopify_id_from_gid(node.id)
            for node in shopify_image_nodes
        }
        failed_media_identifiers = {
            parse_shopify_id_from_gid(node.id)
            for node in shopify_image_nodes
            if node.status == MediaStatus.FAILED
        }
        has_pending_media = any(
            node.status in (MediaStatus.PROCESSING, MediaStatus.UPLOADED)
            for node in shopify_image_nodes
        )
        local_media_identifiers = {
            image.get_external_system_id("shopify", "media")
            for image in ordered_odoo_images
            if image.get_external_system_id("shopify", "media")
        }
        missing_media_identifiers = local_media_identifiers - remote_media_identifiers

        if failed_media_identifiers or missing_media_identifiers:
            self._clear_shopify_media_ids(
                ordered_odoo_images,
                failed_media_identifiers | missing_media_identifiers,
            )
            _logger.info(
                "Shopify media missing/failed for product %s. Scheduling re-export.",
                odoo_product.id,
            )
            odoo_product.shopify_next_export = True
            return False

        if has_pending_media:
            _logger.info(
                "Shopify media still processing for product %s. Scheduling re-export.",
                odoo_product.id,
            )
            odoo_product.shopify_next_export = True
            return False

        return True

    def _schedule_media_reupload(
        self,
        odoo_product: "odoo.model.product_product",
        ordered_odoo_images: "odoo.model.product_image",
        *,
        reason: str,
    ) -> None:
        media_identifiers = {
            image.get_external_system_id("shopify", "media")
            for image in ordered_odoo_images
            if image.get_external_system_id("shopify", "media")
        }
        if media_identifiers:
            self._clear_shopify_media_ids(ordered_odoo_images, media_identifiers)
        _logger.info(
            "Scheduling Shopify media reupload for product %s (%s).",
            odoo_product.id,
            reason,
        )
        odoo_product.shopify_next_export = True

    @staticmethod
    def _clear_shopify_media_ids(
        ordered_odoo_images: "odoo.model.product_image",
        media_identifiers_to_clear: set[str],
    ) -> None:
        if not media_identifiers_to_clear:
            return
        for image in ordered_odoo_images:
            media_identifier = image.get_external_system_id("shopify", "media")
            if media_identifier and media_identifier in media_identifiers_to_clear:
                upsert_external_id(
                    image,
                    system_code="shopify",
                    resource="media",
                    external_id_value=None,
                )

    def is_published_on_all_channels(
        self, publication_channels: list[ProductSetProductSetProductResourcePublicationsV2Nodes]
    ) -> bool:
        for publication_channel in publication_channels:
            if not self.is_published_on_channel(publication_channel.publication):
                return False
        return True

    @staticmethod
    def is_published_on_channel(
        publication_channel: ProductSetProductSetProductResourcePublicationsV2NodesPublication,
    ) -> bool:
        return int(parse_shopify_id_from_gid(publication_channel.id)) in PUBLICATION_CHANNELS.values()

    def _publish_product(self, shopify_product_gid: str) -> None:
        client = self.service.client
        publication_input = [
            PublicationInput(
                publicationId=format_shopify_gid_from_id("Publication", publication_id),
                publishDate=fields.Datetime.now(),
            )
            for publication_id in PUBLICATION_CHANNELS.values()
        ]
        if not self.env["ir.config_parameter"].sudo().get_param("shopify.test_store"):
            client.update_publications(shopify_product_gid, publication_input)

    @staticmethod
    def metafield_from_id_value_key(shopify_id: str, key: str, value: str | int, field_type: str) -> MetafieldInput:
        return MetafieldInput(
            id=(format_shopify_gid_from_id("Metafield", shopify_id) if shopify_id else None),
            namespace="custom",
            key=key,
            value=value,
            type=field_type,
        )

    def _map_odoo_product_to_shopify_product_set_input(
        self,
        odoo_product: "odoo.model.product_product",
        images_need_update: bool = False,
        *,
        force_media_upload: bool = False,
    ) -> ProductSetInput:
        shopify_inventory_item_measurement_input = InventoryItemMeasurementInput(
            weight=WeightInput(
                value=odoo_product.weight,
                unit=WeightUnit.POUNDS,
            ),
        )

        shopify_inventory_item_input = InventoryItemInput(
            cost=Decimal(odoo_product.standard_price),
            measurement=shopify_inventory_item_measurement_input,
            tracked=True,
        )

        shopify_variant_set_input = ProductVariantSetInput(
            id=(
                format_shopify_gid_from_id("ProductVariant", odoo_product.get_external_system_id("shopify", "variant"))
                if odoo_product.get_external_system_id("shopify", "variant")
                else None
            ),
            price=Decimal(odoo_product.list_price),
            sku=format_sku_bin_for_shopify(odoo_product.default_code, odoo_product.bin),
            barcode=odoo_product.mpn or "",
            inventoryItem=shopify_inventory_item_input,
            optionValues=[VariantOptionValueInput(optionName="Title", name="Default Title")],
        )

        shopify_product_set_input = ProductSetInput(
            title=odoo_product.name,
            descriptionHtml=(odoo_product.website_description or "").strip(),
            vendor=odoo_product.manufacturer.name if odoo_product.manufacturer else None,
            productType=odoo_product.part_type.name if odoo_product.part_type else None,
            status=ProductStatus.ACTIVE if odoo_product.qty_available > 0 else ProductStatus.DRAFT,
            variants=[shopify_variant_set_input],
            metafields=[],
            productOptions=[OptionSetInput(name="Title", values=[OptionValueSetInput(name="Default Title")])],
        )

        image_records = odoo_product.images
        should_upload_media = bool(image_records) and (
            not odoo_product.get_external_system_id("shopify", "product")
            or images_need_update
            or force_media_upload
        )
        if should_upload_media:
            image_source_base_url = self.odoo_base_url.rstrip("/")
            ordered_images = image_records.sorted(key=image_order_key)
            shopify_product_set_input.files = [
                FileSetInput(
                    alt=odoo_product.name,
                    contentType=FileContentType.IMAGE,
                    originalSource=f"{image_source_base_url}/web/image/product.image/{odoo_image.id}/image_1920",
                )
                for odoo_image in ordered_images
            ]

        if not odoo_product.get_external_system_id("shopify", "product") or odoo_product.shopify_next_export_quantity_change_amount:
            shopify_product_set_input.variants[0].inventory_quantities = [
                ProductSetInventoryInput(
                    locationId=self.service.first_location_gid,
                    quantity=int(odoo_product.qty_available),
                    name="available",
                )
            ]

        if odoo_product.condition.code:
            shopify_product_set_input.metafields += [
                self.metafield_from_id_value_key(
                    odoo_product.get_external_system_id("shopify", "condition"),
                    "condition",
                    odoo_product.condition.code,
                    LocalizableContentType.SINGLE_LINE_TEXT_FIELD.value.lower(),
                )
            ]

        if odoo_product.part_type and odoo_product.part_type.ebay_category_id:
            shopify_product_set_input.metafields += [
                self.metafield_from_id_value_key(
                    odoo_product.get_external_system_id("shopify", "ebay_category"),
                    "ebay_category_id",
                    str(odoo_product.part_type.ebay_category_id),
                    "number_integer",
                )
            ]

        return shopify_product_set_input

    def _reorder_shopify_media(
        self,
        odoo_product: "odoo.model.product_product",
        shopify_product_gid: str,
        ordered_odoo_images: "odoo.model.product_image",
    ) -> None:
        client = self.service.client

        moves = []
        for new_position, odoo_image in enumerate(ordered_odoo_images):
            media_id = odoo_image.get_external_system_id("shopify", "media")
            if media_id:
                moves.append(
                    MoveInput(
                        id=format_shopify_gid_from_id("MediaImage", media_id),
                        newPosition=new_position,
                    )
                )

        if not moves:
            return

        try:
            response = client.product_reorder_media(id=shopify_product_gid, moves=moves)

            if response.media_user_errors:
                errors_str = ", ".join([f"{err.field}: {err.message}" for err in response.media_user_errors])
                _logger.error(f"Failed to reorder media for product {odoo_product.id}: {errors_str}")
                odoo_product.shopify_next_export = True
            else:
                _logger.info(f"Successfully reordered {len(moves)} images for product {odoo_product.id}")

        except Exception as error:
            _logger.error(f"Error reordering media for product {odoo_product.id}: {error}")
            odoo_product.shopify_next_export = True
