import base64
import io
import logging

from odoo import api, fields, models
from PIL import Image, UnidentifiedImageError

_logger = logging.getLogger(__name__)


class ImageMetadataMixin(models.AbstractModel):
    _name = "image.metadata.mixin"
    _description = "Image Metadata Mixin"
    _inherit = ["image.mixin"]

    image_1920_file_size = fields.Integer(compute="_compute_image_metadata", store=True)
    image_1920_file_size_kb = fields.Float(string="kB", compute="_compute_file_size_kb")
    image_1920_width = fields.Integer(compute="_compute_image_metadata", store=True)
    image_1920_height = fields.Integer(compute="_compute_image_metadata", store=True)
    image_1920_resolution = fields.Char(compute="_compute_image_resolution", string="Image Res")

    @api.depends("image_1920")
    def _compute_image_metadata(self) -> None:
        attachments_by_record = self._fetch_image_attachments()
        for record in self:
            if not record.id:
                self._clear_image_metadata(record)
                continue

            attachment = attachments_by_record.get(record.id)
            if not attachment:
                self._clear_image_metadata(record)
                continue

            record.image_1920_file_size = attachment.file_size or False
            width, height = self._extract_image_dimensions(attachment)
            record.image_1920_width = width
            record.image_1920_height = height

    @api.depends("image_1920_file_size")
    def _compute_file_size_kb(self) -> None:
        for record in self:
            if record.image_1920_file_size:
                record.image_1920_file_size_kb = round(record.image_1920_file_size / 1024, 2)
            else:
                record.image_1920_file_size_kb = False

    @api.depends("image_1920_width", "image_1920_height")
    def _compute_image_resolution(self) -> None:
        for record in self:
            if record.image_1920_width and record.image_1920_height:
                record.image_1920_resolution = f"{record.image_1920_width}x{record.image_1920_height}"
            else:
                record.image_1920_resolution = False

    def _fetch_image_attachments(self) -> dict[int, "odoo.model.ir_attachment"]:
        if not self:
            return {}
        record_ids = [record_id for record_id in self.ids if record_id]
        if not record_ids:
            return {}
        attachments = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", record_ids),
                    ("res_field", "=", "image_1920"),
                ],
                order="id desc",
            )
        )
        attachments_by_record: dict[int, "odoo.model.ir_attachment"] = {}
        for attachment in attachments:
            if attachment.res_id not in attachments_by_record:
                attachments_by_record[attachment.res_id] = attachment
        return attachments_by_record

    def _extract_image_dimensions(self, attachment: "odoo.model.ir_attachment") -> tuple[int | bool, int | bool]:
        if attachment.mimetype and "svg" in attachment.mimetype:
            _logger.info("Image attachment %s is SVG; skipping dimension probe.", attachment.id)
            return False, False
        image_bytes = self._read_attachment_bytes(attachment)
        if not image_bytes:
            return False, False
        try:
            with Image.open(io.BytesIO(image_bytes)) as image_object:
                width, height = image_object.size
            return width, height
        except UnidentifiedImageError:
            _logger.warning("Image attachment %s is not a supported image format.", attachment.id)
        except Exception as error:  # pragma: no cover - defensive logging
            _logger.warning("Failed to read image attachment %s: %s", attachment.id, error)
        return False, False

    @staticmethod
    def _read_attachment_bytes(attachment: "odoo.model.ir_attachment") -> bytes:
        if attachment.store_fname:
            return attachment._file_read(attachment.store_fname) or b""
        if attachment.db_datas:
            db_datas = attachment.db_datas
            try:
                return base64.b64decode(db_datas)
            except Exception as error:  # pragma: no cover - defensive logging
                _logger.warning("Failed to read db datas for attachment %s: %s", attachment.id, error)
                return b""
        return b""

    @staticmethod
    def _clear_image_metadata(record: "odoo.model.image_metadata_mixin") -> None:
        record.image_1920_file_size = False
        record.image_1920_width = False
        record.image_1920_height = False

    @api.model
    def remove_missing_images(self) -> None:
        images_to_remove = self.search([("image_1920", "=", False)])
        placeholder_images = self.search(
            [
                ("image_1920_width", "=", 256),
                ("image_1920_height", "=", 256),
                ("image_1920_file_size", "=", 5966),
            ]
        )

        _logger.info("Found %s missing images and %s placeholder images.", len(images_to_remove), len(placeholder_images))
        images_to_remove |= placeholder_images
        _logger.info("Total images to remove: %s", len(images_to_remove))
        images_to_remove.with_context(skip_shopify_sync=True).unlink()

    def action_open_full_image(self) -> dict:
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/image?model={self._name}&id={self.id}&field=image_1920",
            "target": "new",
        }
