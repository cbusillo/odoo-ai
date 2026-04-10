import base64
import datetime
import logging

from odoo import models
from odoo.exceptions import UserError
from simple_zpl2 import ZPLDocument

_logger = logging.getLogger(__name__)


class LabelMixin(models.AbstractModel):
    _name = "label.mixin"
    _description = "Label Mixin"

    LABEL_SIZE = {"width": 2.2, "height": 1.3}
    LABEL_TEXT_SIZE = {"large": 60, "medium": 35, "small": 20}
    LABEL_PADDING_Y = 10
    LABEL_PADDING_X = 10
    LABEL_CENTER_X = 220
    LABEL_BOTTOM_TEXT_Y = 210
    BARCODE_SIZE = 8

    def _print_labels(
        self,
        labels: list[str] | bytes,
        odoo_job_type: str,
        job_name: str,
        copies: int = 1,
    ) -> None:
        label_data: str | bytes
        if isinstance(labels, list):
            if not labels:
                raise UserError("No labels to print")
            if not isinstance(labels[0], str):
                raise UserError("Invalid label data type")
            label_data = self.combine_labels_base64(labels)
        elif isinstance(labels, bytes):
            label_data = labels
        else:
            _logger.error("Invalid label data type")
            return

        self.env["printnode.interface"].print_label(
            label_data,
            odoo_job_type=odoo_job_type,
            job_name=job_name,
            copies=copies,
        )

    @staticmethod
    def wrap_text(text: str, max_line_length: int) -> list[str]:
        words = text.split(" ")
        lines = []
        current_line: list[str] = []

        for word in words:
            if len(" ".join(current_line + [word])) > max_line_length:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                current_line.append(word)

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def generate_label_base64(
        self,
        text: list[str] | str,
        bottom_text: str | list[str] | None = None,
        barcode: str | None = None,
        quantity: int = 1,
        print_date: bool = True,
    ) -> str:
        if not isinstance(text, list):
            text = [text]

        if bottom_text and not isinstance(bottom_text, list):
            bottom_text = [bottom_text]

        label_width = int(203 * self.LABEL_SIZE["width"])
        column_width = int(label_width / 2)
        label_text_size = self.LABEL_TEXT_SIZE["large"] if text[0] == "" else self.LABEL_TEXT_SIZE["medium"]

        quantity = max(int(quantity), 1)
        label = ZPLDocument()
        label.add_zpl_raw("^BY2")

        current_origin_y = self.LABEL_PADDING_Y

        if print_date:
            today = datetime.date.today()
            formatted_date = f"{today.month}.{today.day}.{today.year}"
            label.add_default_font(
                font_name=0,
                character_height=self.LABEL_TEXT_SIZE["small"],
                character_width=self.LABEL_TEXT_SIZE["small"],
            )
            label.add_field_block(text_justification="C", width=column_width)
            label.add_field_origin(x_pos=self.LABEL_CENTER_X, y_pos=current_origin_y, justification=2)
            label.add_field_data(formatted_date)
            current_origin_y += self.LABEL_TEXT_SIZE["small"]

        for line in text:
            current_line_text_size = (
                self.LABEL_TEXT_SIZE["small"] if line.startswith("(SM)") and len(line.replace("(SM)", "")) > 8 else label_text_size
            )
            line = line.replace("(SM)", "")
            label.add_default_font(
                font_name=0,
                character_height=current_line_text_size,
                character_width=current_line_text_size,
            )
            label.add_field_block(text_justification="C", width=column_width)
            label.add_field_origin(x_pos=self.LABEL_CENTER_X, y_pos=current_origin_y, justification=2)
            label.add_field_data(line)
            current_origin_y += label_text_size

        if bottom_text:
            current_origin_y = self.LABEL_BOTTOM_TEXT_Y
            for line in bottom_text:
                label.add_default_font(
                    font_name=0,
                    character_height=self.LABEL_TEXT_SIZE["small"],
                    character_width=self.LABEL_TEXT_SIZE["small"],
                )
                label.add_field_block(text_justification="C", width=label_width)
                label.add_field_origin(y_pos=current_origin_y, justification=2)
                label.add_field_data(line)
                current_origin_y += self.LABEL_TEXT_SIZE["small"]

        if barcode:
            label.add_field_origin(x_pos=self.LABEL_PADDING_X, y_pos=self.LABEL_PADDING_Y, justification=2)
            # noinspection SpellCheckingInspection
            label.add_zpl_raw(f"^BQN,2,{self.BARCODE_SIZE}^FDQAH" + barcode + "^FS^XZ")

        zpl_text_with_quantity = label.zpl_text * quantity

        return base64.b64encode(zpl_text_with_quantity.encode("utf-8")).decode()

    @staticmethod
    def combine_labels_base64(labels: list[str]) -> str:
        decoded_labels = [base64.b64decode(label).decode() for label in labels]
        combined_labels = "".join(decoded_labels)
        combined_labels_base64 = base64.b64encode(combined_labels.encode()).decode()
        return combined_labels_base64
