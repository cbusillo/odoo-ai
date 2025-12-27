import base64
from odoo import fields, models
from odoo.exceptions import UserError
from typing import Any


class ProductLabelLayout(models.TransientModel):
    _inherit = "product.label.layout"

    print_format = fields.Selection(
        selection_add=[
            ("2x1", "2.25 x 1.25 QR Product"),
            ("2x1bin", "2.25 x 1.25 QR Bin"),
        ],
        ondelete={
            "2x1": "set default",
            "2x1bin": "set default",
        },
        default="2x1",
    )

    def _prepare_report_data(self) -> tuple[str, dict[str, Any]]:
        xml_id, data = super()._prepare_report_data()

        products_data = []
        if "bin" in self.print_format:
            # noinspection SpellCheckingInspection
            xml_id = "product_connect.report_product_template_label_2x1_bin_noprice"

            products = self.product_ids if self.product_ids else self.product_tmpl_ids
            bins = set()
            for product in products:
                if product.bin not in bins:
                    bins.add(product.bin)
                    products_data.append({"bin": product.bin, "current_date": fields.Date.today()})

        elif self.print_format == "2x1":
            # noinspection SpellCheckingInspection
            xml_id = "product_connect.report_product_template_label_2x1_noprice"

            products = self.product_ids if self.product_ids else self.product_tmpl_ids

            for product in products:
                products_data.append(
                    {
                        "current_date": fields.Date.today(),
                        "default_code": product.default_code,
                        "name": product.name,
                        "mpn": (product.mpn.split(",")[0] if product.mpn else ""),
                        "bin": product.bin,
                        "motor_number": (product.motor.motor_number if product.motor else ""),
                        "condition": (product.condition.name if product.condition else ""),
                        "initial_quantity": data["quantity_by_product"].get(product.id, 1),
                    }
                )
        data.update({"products_data": products_data})
        return xml_id, data

    def process(self) -> dict[str, Any]:
        custom_formats = ["2x1", "2x1bin", "4x2motor"]
        # TODO: test if this is still needed.  Will need to be onsite and test motor and product labels
        if self.print_format not in custom_formats or True:
            return super().process()

        self.ensure_one()
        xml_id, data = self._prepare_report_data()
        if not xml_id:
            raise UserError(self.env._("Unable to find report template for %s format", self.print_format))
        report = self.env.ref(xml_id)
        report_pdf_content, content_type = report._render_qweb_pdf(xml_id, data=data)
        report_pdf = base64.b64encode(report_pdf_content).decode()
        report_action = report.report_action(None, data=data)
        report_action["context"] = {"report_pdf": report_pdf}

        return report_action
