import logging
from odoo import models, fields, api
from typing import Literal

_logger = logging.getLogger(__name__)


class ProductInventoryWizardLine(models.TransientModel):
    _name = "product.inventory.wizard.line"
    _description = "Product Inventory Wizard Line"
    _order = "is_selected asc, id desc"

    wizard = fields.Many2one("product.inventory.wizard", ondelete="cascade")
    product = fields.Many2one("product.template")
    default_code = fields.Char(related="product.default_code", readonly=True)
    name = fields.Char(related="product.name", readonly=True)
    original_bin = fields.Char(related="product.bin", string="Original Bin", readonly=True)
    qty_available = fields.Float(related="product.qty_available", readonly=True)
    quantity_scanned = fields.Integer()

    is_selected = fields.Boolean(string="X")


class ProductInventoryWizard(models.TransientModel):
    _name = "product.inventory.wizard"
    _description = "Product Inventory Wizard"

    scan_box = fields.Char(string="Scan", help="Scan or type the SKU/Bin here.")
    products = fields.One2many("product.inventory.wizard.line", "wizard")
    current_bin = fields.Char()
    use_available_quantity_for_labels = fields.Boolean(default=True, string="Use On Hand Quantity for Labels")

    product_labels_to_print = fields.Integer(default=1)
    bin_needs_update = fields.Boolean(compute="_compute_bin_needs_update")
    total_product_labels_to_print = fields.Integer(compute="_compute_total_product_labels_to_print")
    count_of_products_not_selected = fields.Integer(compute="_compute_products_not_selected")

    hide_last_scanned_product = fields.Boolean()
    last_scanned_product = fields.Many2one("product.inventory.wizard.line", readonly=True)
    last_scanned_product_template = fields.Many2one(related="last_scanned_product.product", readonly=True)
    last_scanned_product_qty_available = fields.Float(related="last_scanned_product.qty_available", readonly=True)
    last_scanned_product_bin = fields.Char(related="last_scanned_product.original_bin", readonly=True)
    last_scanned_product_name = fields.Char(related="last_scanned_product.name", readonly=True)
    last_scanned_product_default_code = fields.Char(related="last_scanned_product.default_code", readonly=True)
    last_scanned_product_image = fields.Binary(related="last_scanned_product.product.image_512", readonly=True)
    last_scanned_product_scanned_quantity = fields.Integer(related="last_scanned_product.quantity_scanned", readonly=True)

    @api.depends("products", "products.is_selected")
    def _compute_products_not_selected(self) -> None:
        for wizard in self:
            wizard.count_of_products_not_selected = len(wizard.products.filtered(lambda p: not p.is_selected))

    @api.depends("products", "products.original_bin", "current_bin", "products.is_selected")
    def _compute_bin_needs_update(self) -> None:
        for wizard in self:
            wizard.bin_needs_update = any(p.original_bin != wizard.current_bin for p in wizard.products)

    @api.depends(
        "products",
        "products.qty_available",
        "use_available_quantity_for_labels",
        "product_labels_to_print",
        "products.is_selected",
    )
    def _compute_total_product_labels_to_print(self) -> None:
        for wizard in self:
            wizard.total_product_labels_to_print = sum(
                p.qty_available if wizard.use_available_quantity_for_labels else wizard.product_labels_to_print
                for p in wizard.products.filtered("is_selected")
            )

    def notify_user(
        self, message: "str", title: str | None, message_type: Literal["info", "success", "warning", "danger"] | None
    ) -> None:
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "simple_notification",
            {"title": title or "Notification", "message": message, "sticky": False, "type": message_type or "info"},
        )

    def _handle_product_scan(self) -> bool:
        product_searched = self.env["product.template"].search([("default_code", "=", self.scan_box)], limit=1)
        if not product_searched:
            return False

        product_in_wizard = self.products.filtered(lambda p: p.product == product_searched)
        if product_in_wizard:
            product_in_wizard.quantity_scanned += 1
            if product_in_wizard.quantity_scanned == product_in_wizard.product.qty_available:
                product_in_wizard.is_selected = True
            else:
                product_in_wizard.is_selected = False

        else:
            product_in_wizard = self.env["product.inventory.wizard.line"].create(
                {
                    "wizard": self.id,
                    "product": product_searched.id,
                    "quantity_scanned": 1,
                    "is_selected": True,
                }
            )
            self.products += product_in_wizard

        self.last_scanned_product = product_in_wizard
        return True

    def _handle_bin_scan(self) -> None:
        if self.current_bin and self.products:
            self.action_apply_bin_changes()
        self.current_bin = self.scan_box.strip().upper()
        self._load_bin_products()

    def _load_bin_products(self) -> None:
        products_with_bin_and_quantity = self.env["product.template"].search(
            [("bin", "=", self.current_bin), ("qty_available", ">", 0)]
        )
        lines_created = self.env["product.inventory.wizard.line"].create(
            [
                {
                    "wizard": self.id,
                    "product": product.id,
                    "quantity_scanned": 0,
                    "is_selected": False,
                }
                for product in products_with_bin_and_quantity
            ]
        )
        commands = [(5, 0, 0)] + [(4, line.id) for line in lines_created]
        self.write({"products": commands})

    @api.onchange("scan_box")
    def _onchange_scan_box(self) -> None | dict[str, dict[str, str]]:
        if not self.scan_box:
            return None

        if self.scan_box[0].isalpha():
            self._handle_bin_scan()
        else:
            if not self._handle_product_scan():
                return {
                    "warning": {
                        "title": "Item not found",
                        "message": f"SKU {self.scan_box} not found in Odoo.",
                    }
                }

        self.scan_box = ""
        return None

    def action_apply_bin_changes(self) -> None:
        if not self.current_bin:
            self.notify_user("No bin selected to apply.", "No bin to apply", "warning")
            return

        products_to_update = self.products.filtered(lambda p: p.original_bin != self.current_bin)
        if products_to_update:
            products_to_update.mapped("product").write({"bin": self.current_bin})
            self.notify_user(
                f"Updated bin location to {self.current_bin} for {len(products_to_update)} products",
                "Success",
                "success",
            )
            return
        self.notify_user("No products needed bin update.", "No changes", "info")

    def action_print_product_labels(
        self,
    ) -> "odoo.values.ir_actions_client":
        product_ids_selected = self.products.filtered(lambda p: p.is_selected).mapped("product.id")
        products_to_print = self.env["product.template"].search([("id", "in", product_ids_selected)])
        if not products_to_print:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "No labels to print",
                    "message": f"No products selected to print labels.",
                    "type": "warning",
                },
            }
        for product in products_to_print:
            quantity_to_print = product.qty_available if self.use_available_quantity_for_labels else self.product_labels_to_print
            if quantity_to_print:
                product.print_product_labels(quantity_to_print=quantity_to_print)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Success",
                "message": f"Sent label(s) for {len(products_to_print)} product(s) to printer.",
                "type": "success",
            },
        }

    def action_print_bin_label(self) -> "odoo.values.ir_actions_client":
        if not self.current_bin:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "No bin to print",
                    "message": f"No bin selected to print labels.",
                    "type": "warning",
                },
            }
        label_data = ["", "Bin: ", self.current_bin]
        label = self.products.product.generate_label_base64(label_data, barcode=self.current_bin)
        self.products.product._print_labels([label], odoo_job_type="product_label", job_name="Bin Label")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Success",
                "message": f"Sent bin label for {self.current_bin} to printer.",
                "type": "success",
            },
        }
