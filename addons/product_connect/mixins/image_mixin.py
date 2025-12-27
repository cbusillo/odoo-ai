import logging

from PIL import Image, UnidentifiedImageError
from odoo import models, fields, api
from odoo.tools import config
from pathlib import Path

from ..services.shopify.helpers import SyncMode

_logger = logging.getLogger(__name__)


class ImageMixin(models.AbstractModel):
    _description = "Image Mixin"
    _inherit = "image.mixin"

    attachment = fields.Many2one("ir.attachment", compute="_compute_attachment", store=True)
    image_1920_file_size = fields.Integer(related="attachment.file_size", store=True)
    image_1920_file_size_kb = fields.Float(string="kB", compute="_compute_file_size_kb", store=True)
    image_1920_width = fields.Integer(compute="_compute_image_dimensions", store=True)
    image_1920_height = fields.Integer(compute="_compute_image_dimensions", store=True)
    image_1920_resolution = fields.Char(compute="_compute_image_dimensions", store=True, string="Image Res")
    initial_index = fields.Integer()
    shopify_media_id = fields.Char(string="Shopify Media ID")

    def _mark_for_shopify_product_export(self) -> None:
        products_to_mark = self.env["product.product"]
        for record in self:
            if isinstance(record, type(self.env["product.image"])):
                products_to_mark |= record.product_variant_id

        if products_to_mark:
            products_to_mark.write({"shopify_next_export": True})

            if not self.env.context.get("skip_immediate_sync"):
                self.env["shopify.sync"].create_and_run_async({"mode": SyncMode.EXPORT_CHANGED_PRODUCTS})

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> "odoo.model.image_mixin":
        records = super().create(vals_list)
        if records._name == "product.image" and not self.env.context.get("skip_shopify_sync"):
            records._mark_for_shopify_product_export()
        return records

    def write(self, vals: dict) -> "odoo.model.image_mixin":
        res = super().write(vals)
        if {"image_1920", "sequence"} & vals.keys() and not self.env.context.get("skip_shopify_sync"):
            self._mark_for_shopify_product_export()
        return res

    def unlink(self) -> None:
        if not self.env.context.get("skip_shopify_sync"):
            self._mark_for_shopify_product_export()
        super().unlink()

    @api.depends("image_1920")
    def _compute_attachment(self) -> None:
        for record in self:
            record.attachment = self.env["ir.attachment"].search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", record.id),
                    ("res_field", "=", "image_1920"),
                ],
                limit=1,
            )

    @api.depends("attachment.file_size")
    def _compute_file_size_kb(self) -> None:
        for image in self:
            image.image_1920_file_size_kb = round(image.image_1920_file_size / 1024, 2)

    @api.depends("attachment.store_fname")
    def _compute_image_dimensions(self) -> None:
        for record in self:
            db_name = self.env.cr.dbname
            filestore_path = Path(config.filestore(db_name))
            if not record.attachment.store_fname:
                self._reset_image_details(record)
                continue
            image_path = filestore_path / Path(record.attachment.store_fname)

            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    record.image_1920_width = width
                    record.image_1920_height = height
                    record.image_1920_resolution = f"{width}x{height}"
            except FileNotFoundError:
                _logger.warning(f"Image: {record} file not found\n {image_path}")
                self._reset_image_details(record)
            except UnidentifiedImageError as e:
                if "svg" in record.attachment.mimetype:
                    _logger.info(f"Image: {record.attachment} is an SVG")
                    self._reset_image_details(record)
                else:
                    _logger.warning(f"Image: {record.attachment} unidentified image {e}")
                    raise e

    @staticmethod
    def _reset_image_details(image: "odoo.model.image_mixin") -> None:
        image.write(
            {
                "image_1920_file_size_kb": None,
                "image_1920_width": None,
                "image_1920_height": None,
                "image_1920_resolution": None,
            }
        )

    @api.model
    def remove_missing_images(self) -> None:
        images_to_remove = self.search([("image_1920", "=", False)])
        placeholder_images = self.search([("image_1920_resolution", "=", "256x256"), ("image_1920_file_size", "=", 5966)])

        _logger.info(f"Found {len(images_to_remove)} missing images and {len(placeholder_images)} placeholder images.")
        images_to_remove |= placeholder_images
        _logger.info(f"Total images to remove: {len(images_to_remove)}")
        images_to_remove.with_context(skip_shopify_sync=True).unlink()

    def action_open_full_image(self) -> dict:
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/odoo/image?model={self._name}&id={self.id}&field=image_1920",
            "target": "new",
        }
