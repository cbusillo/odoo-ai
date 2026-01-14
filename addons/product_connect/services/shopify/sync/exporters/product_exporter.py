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
from ...gql.enums import ProductStatus, WeightUnit, LocalizableContentType
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

        latest_image_date = get_latest_image_write_date(odoo_product)
        images_need_update = latest_image_date > (odoo_product.shopify_last_exported_at or datetime.min)
        all_images_have_media_id = all(img.shopify_media_id for img in odoo_product.images) if odoo_product.images else False

        _logger.info(
            f"Exporting product {odoo_product.id} - images need update: {images_need_update}, "
            f"all have media IDs: {all_images_have_media_id}"
        )

        if (
            images_need_update
            and all_images_have_media_id
            and odoo_product.shopify_product_id
            and not odoo_product.shopify_next_export
        ):
            ordered_odoo_images = sorted(odoo_product.images, key=image_order_key)
            shopify_product_gid = format_shopify_gid_from_id("Product", odoo_product.shopify_product_id)
            self._reorder_shopify_media(odoo_product, shopify_product_gid, ordered_odoo_images)
            odoo_product.shopify_last_exported_at = fields.Datetime.now()
            return

        shopify_product_set_input = self._map_odoo_product_to_shopify_product_set_input(odoo_product, images_need_update)

        shopify_product_gid = (
            format_shopify_gid_from_id("Product", odoo_product.shopify_product_id) if odoo_product.shopify_product_id else None
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

        flags_and_ids: "odoo.values.product_product" = {
            "shopify_product_id": parse_shopify_id_from_gid(shopify_product.id),
            "shopify_variant_id": parse_shopify_id_from_gid(shopify_product.variants.nodes[0].id),
            "shopify_condition_id": parse_shopify_id_from_gid(condition_metafield.id) if condition_metafield else None,
            "shopify_ebay_category_id": (
                parse_shopify_id_from_gid(ebay_category_id_metafield.id) if ebay_category_id_metafield else None
            ),
            "shopify_next_export": False,
            "shopify_next_export_quantity_change_amount": 0,
        }
        write_if_changed(odoo_product, flags_and_ids)
        odoo_product.shopify_last_exported_at = fields.Datetime.now()

    @staticmethod
    def _sync_images_after_export(odoo_product: "odoo.model.product_product", shopify_product: ProductSetProductSetProduct) -> None:
        shopify_images = [image for image in shopify_product.media.nodes if image.status != MediaStatus.FAILED]
        if not shopify_images:
            return

        ordered_odoo_images = sorted(odoo_product.images, key=image_order_key)

        if len(ordered_odoo_images) != len(shopify_images):
            _logger.info(
                f"Mismatch immediately after export ({len(ordered_odoo_images)} Odoo vs {len(shopify_images)} Shopify). Scheduling retry."
            )
            odoo_product.shopify_next_export = True
            return

        for odoo_image, shopify_image in zip(ordered_odoo_images, shopify_images):
            media_id = parse_shopify_id_from_gid(shopify_image.id)
            if not odoo_image.shopify_media_id:
                odoo_image.shopify_media_id = media_id

            if shopify_image.alt and odoo_image.name != shopify_image.alt:
                odoo_image.name = shopify_image.alt

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
        self, odoo_product: "odoo.model.product_product", images_need_update: bool = False
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
                format_shopify_gid_from_id("ProductVariant", odoo_product.shopify_variant_id)
                if odoo_product.shopify_variant_id
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

        if not odoo_product.shopify_product_id or images_need_update:
            shopify_product_set_input.files = [
                FileSetInput(
                    alt=odoo_product.name,
                    originalSource=self.odoo_base_url + "/odoo/image/product.image/" + str(odoo_image.id) + "/image_1920",
                )
                for odoo_image in sorted(odoo_product.images, key=image_order_key)
            ]

        if not odoo_product.shopify_product_id or odoo_product.shopify_next_export_quantity_change_amount:
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
                    odoo_product.shopify_condition_id,
                    "condition",
                    odoo_product.condition.code,
                    LocalizableContentType.SINGLE_LINE_TEXT_FIELD.value.lower(),
                )
            ]

        if odoo_product.part_type and odoo_product.part_type.ebay_category_id:
            shopify_product_set_input.metafields += [
                self.metafield_from_id_value_key(
                    odoo_product.shopify_ebay_category_id,
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
        ordered_odoo_images: list["odoo.model.product_image"],
    ) -> None:
        client = self.service.client

        moves = []
        for new_position, odoo_image in enumerate(ordered_odoo_images):
            if odoo_image.shopify_media_id:
                moves.append(
                    MoveInput(
                        id=format_shopify_gid_from_id("MediaImage", odoo_image.shopify_media_id),
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
