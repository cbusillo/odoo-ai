import logging
import re
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError
from typing import Any, Self

from ..services.shopify.helpers import SyncMode

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "label.mixin", "notification.manager.mixin", "transaction.mixin"]
    _description = "Product"
    _order = "create_date desc"
    _sql_constraints = [
        ("default_code_uniq", "unique(default_code)", "SKU must be unique."),
        ("shopify_product_id_uniq", "unique(shopify_product_id)", "Shopify Product ID must be unique."),
    ]

    source = fields.Selection(
        [("import", "Import Product"), ("motor", "Motor Product"), ("shopify", "Shopify Product"),
         ("standard", "Standard Product")],
        default="standard",
        required=False,
        index=True,
    )

    SKU_PATTERN = re.compile(r"^\d{4,8}$")

    is_ready_for_sale = fields.Boolean(tracking=True, index=True, default=True)
    is_ready_for_sale_last_enabled_date = fields.Datetime(index=True,
                                                          help="Timestamp when this product was last enabled for sale")
    name_with_tags_length = fields.Integer(compute="_compute_name_with_tags_length")

    motor = fields.Many2one("motor", ondelete="restrict", readonly=True, index=True)
    motor_tests = fields.One2many("motor.test", related="motor.tests")
    default_code = fields.Char("SKU", index=True, copy=False)
    standard_price = fields.Float(
        string="Cost",
        tracking=True,
        help="Cost that was paid for the product, normally calculated from the motor cost.  Must be at least $0.01 for "
             "enabling motor products.",
    )
    initial_cost_total = fields.Float(compute="_compute_initial_cost_total", store=True)
    list_price = fields.Float(string="Price", tracking=True, default=0)
    initial_price_total = fields.Float(compute="_compute_initial_price_total", store=True)
    is_price_or_cost_missing = fields.Boolean(compute="_compute_is_price_or_cost_missing", store=True, index=True)

    create_date = fields.Datetime(index=True)

    images = fields.One2many("product.image", "product_tmpl_id")
    image_count = fields.Integer(compute="_compute_image_count", store=True)
    image_icon = fields.Binary(related="images.image_1920", string="Image Icon")

    mpn = fields.Char(string="MPN", index=True)
    first_mpn = fields.Char(compute="_compute_first_mpn", store=True)
    manufacturer = fields.Many2one("product.manufacturer", index=True)
    vendor = fields.Many2one("res.partner", domain=[("supplier_rank", ">", 0)], )
    part_type = fields.Many2one("product.type", index=True)
    part_type_name = fields.Char(related="part_type.name", store=True, index=True, string="Part Type Name")

    condition = fields.Many2one("product.condition", index=True)

    length = fields.Integer()
    width = fields.Integer()
    height = fields.Integer()

    bin = fields.Char(index=True)
    initial_quantity = fields.Float(string="Quantity", index=True)

    has_recent_messages = fields.Boolean(compute="_compute_has_recent_messages", store=True)

    image_1920 = fields.Image(compute="_compute_image_1920", inverse="_inverse_image_1920", store=True)

    motor_product_template = fields.Many2one("motor.product.template", ondelete="restrict", readonly=True)
    motor_product_template_name = fields.Char(related="motor_product_template.name", string="Template Name")
    motor_product_computed_name = fields.Char(compute="_compute_motor_product_computed_name", store=True)
    is_qty_listing = fields.Boolean(related="motor_product_template.is_quantity_listing")

    reference_product = fields.Many2one("product.template", compute="_compute_reference_product", store=True,
                                        index=True)

    dismantle_notes = fields.Text()
    template_name_with_dismantle_notes = fields.Char(compute="_compute_template_name_with_dismantle_notes", store=False)
    tech_result = fields.Many2one(comodel_name="motor.dismantle.result", ondelete="restrict", tracking=True)

    is_listable = fields.Boolean(default=False, index=True, tracking=True)

    is_dismantled = fields.Boolean(default=False, tracking=True, string="Dismantled", index=True)
    is_dismantled_qc = fields.Boolean(default=False, tracking=True, string="Dismantled QC")
    is_cleaned = fields.Boolean(default=False, tracking=True, string="Cleaned", index=True)
    is_cleaned_qc = fields.Boolean(default=False, tracking=True, string="Cleaned QC")
    is_picture_taken = fields.Boolean(default=False, tracking=True, string="Picture Taken")
    is_pictured = fields.Boolean(default=False, tracking=True, string="Pictured", index=True)
    is_pictured_qc = fields.Boolean(default=False, tracking=True, string="Pictured QC")
    is_scrap = fields.Boolean(default=False, tracking=True, string="Scrap", index=True)
    is_ready_to_list = fields.Boolean(compute="_compute_ready_to_list", store=True, index=True)

    repairs = fields.One2many(related="product_variant_ids.repairs")
    open_repair_count = fields.Integer(compute="_compute_open_repair_count", store=True, index=True)
    repair_state = fields.Selection(
        [
            ("none", "None"),
            ("may_need_repair", "May Need Repair"),
            ("in_repair", "In Repair"),
            ("repaired", "Repaired"),
            ("cancelled", "Cancelled Repair"),
        ],
        compute="_compute_repair_state",
        store=True,
        tracking=True,
    )

    shopify_product_id = fields.Char(
        related="product_variant_ids.shopify_product_id",
        string="Shopify Product ID",
        readonly=True,
        store=True,
    )
    shopify_product_url = fields.Char(compute="_compute_shopify_urls", store=True, string="Shopify Product Link")
    shopify_product_admin_url = fields.Char(compute="_compute_shopify_urls", store=True,
                                            string="Shopify Product Admin Link")

    @api.model
    def default_get(self, fields_list: list[str]) -> dict[str, Any]:
        defaults = super().default_get(fields_list)

        source = self.env.context.get("default_source")
        if "default_code" in fields_list and source == "import":
            defaults["default_code"] = self.get_next_sku()

        return defaults

    # noinspection PyShadowingNames
    @api.model
    def read_group(
            self,
            domain: list,
            fields: list,
            groupby: str | list[str],
            offset: int = 0,
            limit: int | None = None,
            orderby: str | None = "",
            lazy: bool = True,
    ) -> list[dict[str, Any]]:
        groups = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        fields_to_sum_with_qty = {"list_price", "standard_price"}
        if not fields_to_sum_with_qty.intersection(fields):
            return groups
        for group in groups:
            if "__domain" in group:
                group["list_price"] = sum(
                    product["list_price"] * product["initial_quantity"] for product in self.search(group["__domain"])
                )
                group["standard_price"] = sum(
                    product["standard_price"] * product["initial_quantity"] for product in
                    self.search(group["__domain"])
                )

        return groups

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.product_template"]) -> Self:
        for vals in vals_list:
            source = self._context.get("default_source") or vals.get("source")
            if source:
                vals["source"] = source
                if source == "import":
                    vals["type"] = "consu"
                    vals["is_ready_for_sale"] = False
                    vals["is_ready_to_list"] = True
                    vals["is_storable"] = True
                if source == "motor":
                    vals["is_ready_for_sale"] = False

            if "type" in vals and vals["type"] == "service":
                vals["is_ready_for_sale"] = False
                vals["is_ready_to_list"] = False
                continue

            if not vals.get("default_code") and vals.get("type") == "consu":
                vals["default_code"] = self.get_next_sku()

        products = super().create(vals_list)
        for product in products:
            if product.source == "motor":
                product.name = product.motor_product_computed_name

        if self.env.context.get("skip_shopify_sync"):
            return products

        if consumable_products := products.filtered(
                lambda p: p.type == "consu" and p.is_ready_for_sale and p.is_published):
            variant_ids = consumable_products.mapped("product_variant_ids").ids
            self.env["shopify.sync"].create_and_run_async(
                {"mode": SyncMode.EXPORT_BATCH_PRODUCTS, "odoo_products_to_sync": [(6, 0, variant_ids)]}
            )

        return products

    def write(self, vals: "odoo.values.product_template") -> bool:
        qc_reset_fields = {"is_dismantled", "is_cleaned", "is_pictured"}
        ui_refresh_fields = {
            "is_listable",
            "is_dismantled",
            "is_dismantled_qc",
            "is_cleaned",
            "is_cleaned_qc",
            "is_pictured",
            "is_pictured_qc",
            "is_scrap",
            "bin",
            "weight",
        }

        write_results: list[bool] = []

        for product in self:
            vals_to_write = vals.copy()

            for field in qc_reset_fields:
                if field in vals_to_write and not vals_to_write[field]:
                    vals_to_write[f"{field}_qc"] = False

            if "is_pictured" in vals_to_write and vals_to_write["is_pictured"] and not product.images:
                vals_to_write["is_pictured"] = False
                self.env["bus.bus"]._sendone(
                    self.env.user.partner_id,
                    "simple_notification",
                    {
                        "title": "Missing Pictures",
                        "message": "Please upload pictures before proceeding.",
                        "sticky": False,
                    },
                )

            if "is_pictured" in vals_to_write and vals_to_write["is_pictured"]:
                vals_to_write["is_picture_taken"] = True

            if "is_dismantled" in vals_to_write and vals_to_write["is_dismantled"]:
                message_text = f"Product '{product.motor_product_template_name}' dismantled"
                product.motor.message_post(body=message_text, message_type="comment", subtype_xmlid="mail.mt_note")

            if "tech_result" in vals_to_write:
                tech_result = self.env["motor.dismantle.result"].browse(vals_to_write["tech_result"]).name
                message_text = f"Product '{product.motor_product_template_name}' tech result: {tech_result}"
                product.motor.message_post(body=message_text, message_type="comment", subtype_xmlid="mail.mt_note")

            if "is_scrap" in vals_to_write:
                if vals_to_write["is_scrap"]:
                    vals_to_write.update(
                        {
                            "is_dismantled": False,
                            "is_dismantled_qc": False,
                            "is_cleaned": False,
                            "is_cleaned_qc": False,
                            "is_pictured": False,
                            "is_pictured_qc": False,
                        }
                    )

                if product.motor:
                    action = "marked as scrap" if vals_to_write["is_scrap"] else "unmarked as scrap"
                    message_text = f"Product '{product.motor_product_template_name}' {action}"
                    product.motor.message_post(body=message_text, message_type="comment", subtype_xmlid="mail.mt_note")

            # Update last enabled date when is_ready_for_sale changes from falsey to True
            if vals_to_write.get("is_ready_for_sale") and not product.is_ready_for_sale:
                vals_to_write["is_ready_for_sale_last_enabled_date"] = fields.Datetime.now()

            write_results.append(super(ProductTemplate, product).write(vals_to_write))

            if product.image_count < 1 and (product.is_pictured or product.is_pictured_qc):
                product.is_pictured = False
                product.is_pictured_qc = False

            if product.motor and any(f in vals_to_write for f in ui_refresh_fields):
                product.motor.notify_changes()

        if not self.env.context.get("skip_shopify_sync"):
            if (
                    variant_ids := self.filtered(lambda p: p.type == "consu" and p.is_ready_for_sale and p.is_published)
                            .mapped("product_variant_ids")
                            .ids
            ):
                commands = [(4, vid) for vid in variant_ids]
                self.env["shopify.sync"].create_and_run_async(
                    {"mode": SyncMode.EXPORT_BATCH_PRODUCTS, "odoo_products_to_sync": commands}
                )

        return all(write_results)

    def _track_template(self, changes: set[str]) -> dict[str, tuple[str, dict]]:
        self.ensure_one()
        result = super()._track_template(changes)
        if "repair_state" not in changes:
            return result
        template = self.env.ref(
            "product_connect.mail_template_repair_state_change",
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning("Missing mail template product_connect.mail_template_repair_state_change")
            return result
        result["repair_state"] = (
            "product_connect.mail_template_repair_state_change",
            {},
        )
        return result

    @api.depends("initial_quantity", "list_price")
    def _compute_initial_price_total(self) -> None:
        for product in self:
            product.initial_price_total = product.initial_quantity * product.list_price

    @api.depends("initial_quantity", "standard_price")
    def _compute_initial_cost_total(self) -> None:
        for product in self:
            product.initial_cost_total = product.initial_quantity * product.standard_price

    @api.depends("list_price", "standard_price")
    def _compute_is_price_or_cost_missing(self) -> None:
        for product in self:
            product.is_price_or_cost_missing = not product.list_price or not product.standard_price

    def _compute_name_with_tags_length(self) -> None:
        for product in self:
            name = product.replace_template_tags(product.name or "")
            name = name.replace("{mpn}", product.first_mpn)
            product.name_with_tags_length = len(name)

    def _compute_repairs(self) -> None:
        for product in self:
            variants = product.product_variant_ids
            product.repairs = self.env["repair.order"].search([("product_id", "in", variants.ids)])

    @api.depends("repairs.state")
    def _compute_open_repair_count(self) -> None:
        for product in self:
            product.open_repair_count = self.env["repair.order"].search_count(
                [("product_id", "in", product.product_variant_ids.ids), ("state", "not in", ["done", "cancel"])]
            )

    @api.depends(
        "motor_product_template.repair_by_tech_results",
        "motor_product_template.repair_by_tests",
        "tech_result",
        "motor.tests.computed_result",
        "repairs.state",
    )
    def _compute_repair_state(self) -> None:
        for product in self:
            if not product.motor_product_template:
                product.repair_state = "none"
                continue

            if product.repairs.filtered(lambda r: r.state not in ["done", "cancel"]):
                product.repair_state = "in_repair"
                continue
            if product.repairs.filtered(lambda r: r.state == "done"):
                product.repair_state = "repaired"
                continue
            if product.repairs.filtered(lambda r: r.state == "cancel"):
                product.repair_state = "cancelled"
                continue

            may_need_repair = any(
                [
                    product.tech_result in product.motor_product_template.repair_by_tech_results,
                    product.motor._should_repair_product(product.motor, product.motor_product_template),
                ]
            )
            product.repair_state = "may_need_repair" if may_need_repair else "none"

    @api.depends("product_template_image_ids")
    def _compute_image_1920(self) -> None:
        for product in self:
            if product.product_template_image_ids:
                product.image_1920 = product.product_template_image_ids[0].image_1920
            else:
                product.image_1920 = False

    def _inverse_image_1920(self) -> None:
        for product in self:
            if product.product_template_image_ids:
                product.product_template_image_ids[0].write({"image_1920": product.image_1920})

            elif product.image_1920:
                self.env["product.image"].create(
                    {
                        "product_tmpl_id": product.id,
                        "image_1920": product.image_1920,
                        "name": f"{product.name}_image",
                    }
                )

    @api.depends("shopify_product_id")
    def _compute_shopify_urls(self) -> None:
        for product in self:
            if product.shopify_product_id:
                shop_url_key = self.env["ir.config_parameter"].get_param("shopify.shop_url_key")
                product.shopify_product_admin_url = (
                    f"https://admin.shopify.com/store/{shop_url_key}/products/{product.shopify_product_id}"
                )
                product.shopify_product_url = f"https://{shop_url_key}.myshopify.com/products/{product.shopify_product_id}"
            else:
                product.shopify_product_admin_url = False
                product.shopify_product_url = False

    @api.constrains("default_code")
    def check_sku(self) -> None:
        if self.env.context.get("skip_sku_check"):
            return
        for product in self:
            if not product.default_code or product.type != "consu":
                continue
            if not self.SKU_PATTERN.fullmatch(product.default_code):
                raise ValidationError(self.env._("SKU must be 4-8 digits."))

    @api.constrains("source", "type")
    def _check_source_required_for_consumable(self) -> None:
        for product in self:
            if product.type == "consu" and not product.source:
                raise ValidationError(self.env._("Source is required for consumable products."))

    def get_next_sku(self) -> str:
        sequence_model: "odoo.model.ir_sequence" = self.env["ir.sequence"]
        sequence = sequence_model.search([("code", "=", "product.template.default_code")], limit=1)
        if not sequence:
            raise ValidationError("SKU sequence missing.")

        max_sku = "9" * sequence.padding
        new_sku = sequence_model.next_by_code("product.template.default_code")
        while new_sku and new_sku <= max_sku:
            # sometimes sudo or with_context trigger even though they are correct.
            # noinspection PyUnresolvedReferences
            if not (
                    self.env["product.template"].sudo().with_context(active_test=False).search(
                        [("default_code", "=", new_sku)], limit=1)
            ):
                return new_sku
            new_sku = sequence_model.next_by_code("product.template.default_code")

        raise ValidationError("SKU limit reached.")

    @api.constrains("length", "width", "height")
    def _check_dimension_values(self) -> None:
        for product in self:
            dimension_values = [product.length, product.width, product.height]
            for dimension in dimension_values:
                if dimension and len(str(abs(int(dimension)))) > 2:
                    raise ValidationError("Dimensions cannot exceed 2 digits.")

    @api.depends("mpn")
    def _compute_first_mpn(self) -> None:
        for product in self:
            list_of_mpns = product.get_list_of_mpns()
            if list_of_mpns:
                product.first_mpn = product.get_list_of_mpns()[0]
            else:
                product.first_mpn = ""

    def get_list_of_mpns(self) -> list[str]:
        self.ensure_one()
        if not self.mpn or not self.mpn.strip():
            return []
        mpn_parts = re.split(r"[, ]", self.mpn)
        return [mpn.strip() for mpn in mpn_parts if mpn.strip()]

    @api.depends("images.image_1920")
    def _compute_image_count(self) -> None:
        for product in self:
            product.image_count = self.env["ir.attachment"].search_count(
                [
                    ("res_model", "=", product.images._name),
                    ("res_id", "in", product.images.ids),
                    ("res_field", "=", "image_1920"),
                    ("file_size", ">", 0),
                ]
            )

    @api.depends("message_ids")
    def _compute_has_recent_messages(self) -> None:
        recent_cutoff = fields.Datetime.now() - timedelta(minutes=30)
        recent_messages = self.env["mail.message"].search(
            [
                ("model", "=", self._name),
                ("res_id", "in", self.ids),
                ("create_date", ">=", recent_cutoff),
                ("subject", "ilike", "Import Error"),
            ]
        )

        product_ids_with_recent_messages = recent_messages.mapped("res_id")

        for product in self:
            product.has_recent_messages = product.id in product_ids_with_recent_messages

    @api.constrains("mpn", "bin")
    def _check_mpn_bin(self) -> None:
        self._onchange_format_mpn_upper()
        self._onchange_format_bin_upper()

    @api.onchange("mpn")
    def _onchange_format_mpn_upper(self) -> None:
        for product in self.filtered(lambda p: p.mpn and p.mpn.upper() != p.mpn):
            product.mpn = product.mpn.upper()

    @api.onchange("bin")
    def _onchange_format_bin_upper(self) -> None:
        for product in self.filtered(lambda p: p.bin and p.bin.upper() != p.bin):
            product.bin = product.bin.upper()

    def find_new_products_with_same_mpn(self) -> "odoo.model.product_template":
        existing_products = self.filtered(lambda p: p.default_code != self.default_code and p.mpn == self.mpn)
        return existing_products

    def check_for_conflicting_products(self) -> None:
        for product in self:
            existing_products = product.find_new_products_with_same_mpn()
            if existing_products:
                raise UserError(
                    f"Product(s) with the same MPN already exist: {', '.join(existing_products.mapped('default_code'))}")

    @api.model
    def _check_fields_and_images(self, product: "odoo.model.product_template") -> list[str]:
        missing_fields = self._check_missing_fields(product)
        missing_fields += self._check_missing_images_or_small_images(product.images)
        return missing_fields

    @api.model
    def _check_missing_fields(self, product: "odoo.model.product_template") -> list[str]:
        required_fields = [
            product._fields["default_code"].name,
            product._fields["name"].name,
            product._fields["website_description"].name,
            product._fields["standard_price"].name,
            product._fields["list_price"].name,
            product._fields["initial_quantity"].name,
            product._fields["bin"].name,
            product._fields["weight"].name,
            product._fields["manufacturer"].name,
        ]

        missing_fields = [field for field in required_fields if not product[field]]

        return missing_fields

    @staticmethod
    def _check_missing_images_or_small_images(all_images: "odoo.model.product_image") -> list[str]:
        min_image_size = 50
        min_image_resolution = 1920
        missing_fields = []
        images_with_data = all_images.filtered(lambda i: i.image_1920)

        if not images_with_data:
            missing_fields.append("images")

        for image in images_with_data:
            if image.image_1920_file_size_kb < min_image_size:
                missing_fields.append(
                    f"Image ({image.initial_index}) too small ({image.image_1920_file_size_kb}kB < {min_image_size}kB minimum size)"
                )
            if image.image_1920_width < min_image_resolution - 1 and image.image_1920_height < min_image_resolution - 1:
                missing_fields.append(
                    f"Image ({image.initial_index}) too small ({image.image_1920_width}x{image.image_1920_height} < "
                    f"{min_image_resolution}x{min_image_resolution} minimum size)"
                )

        return missing_fields

    def _post_missing_data_message(self, products: "odoo.model.product_template") -> None:
        for product in products:
            missing_fields = self._check_fields_and_images(product)
            if missing_fields:
                missing_fields_display = ", ".join(
                    self._fields[f].string if "image" not in f.lower() else f for f in missing_fields)
                product.message_post(
                    body=f"Missing data: {missing_fields_display}",
                    subject="Import Error",
                    subtype_id=self.env.ref("mail.mt_note").id,
                    partner_ids=[self.env.user.partner_id.id],
                )

        self._safe_commit()

    def print_bin_labels(self) -> None:
        unique_bins = [
            bin_location
            for bin_location in set(self.mapped("bin"))
            if bin_location and bin_location.strip().lower() not in ["", " ", "back"]
        ]
        unique_bins.sort()
        labels = []
        for product_bin in unique_bins:
            label_data = ["", "Bin: ", product_bin]
            label = self.generate_label_base64(label_data, barcode=product_bin)
            labels.append(label)

        self._print_labels(
            labels,
            odoo_job_type="product_label",
            job_name="Bin Label",
        )

    def print_product_labels(
            self, use_available_qty: bool = False, quantity_to_print: int = 1, printer_job_type: str = "product_label"
    ) -> None:
        labels = []
        for product in self:
            name = product.name.replace("{mpn}", "")
            name = re.sub(r"\s+", " ", name.strip())
            name = product.replace_template_tags(name or "")
            label_data = [
                f"SKU: {product.default_code}",
                "MPN: ",
                f"(SM){product.first_mpn or ''}",
                f"{product.motor.motor_number or '       '}",
                product.condition.name if product.condition else "",
            ]
            quantity_field_name = "qty_available" if product.is_ready_for_sale else "initial_quantity"
            quantity = getattr(product, quantity_field_name, 1) if use_available_qty else quantity_to_print
            label = self.generate_label_base64(
                label_data,
                bottom_text=self.wrap_text(name, 50),
                barcode=product.default_code,
                quantity=quantity,
            )
            labels.append(label)
        self._print_labels(
            labels,
            odoo_job_type=printer_job_type,
            job_name="Product Label",
        )

    def enable_ready_for_sale(self) -> None:
        products_missing_data = self.filtered(lambda p: p._check_fields_and_images(p))
        self._post_missing_data_message(products_missing_data)
        products_to_enable = self.filtered(lambda p: p.is_ready_to_list or p.source == "import")
        ready_to_enable_products = products_to_enable - products_missing_data

        if not ready_to_enable_products:
            raise UserError("No products are ready to sell. Check messages for details.")

        if products_missing_data:
            message = f"{len(products_missing_data)} product(s) are not ready to sell. Check messages for details."
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {"title": "Import Warning", "message": message, "sticky": False},
            )

        ready_to_enable_products.filtered(
            lambda p: p.condition and p.condition.name == "new").check_for_conflicting_products()

        for product in ready_to_enable_products:
            website_description = product.replace_template_tags(product.website_description or "")
            website_description = website_description.replace("{mpn}", " ".join(product.get_list_of_mpns()))
            product.website_description = website_description

            name = product.replace_template_tags(product.name or "")
            name = name.replace("{mpn}", product.first_mpn)
            product.name = name
            product.is_published = True
            product.product_variant_id.shopify_next_export = True

            product_variant = self.env["product.product"].search([("product_tmpl_id", "=", product.id)], limit=1)
            if product_variant:
                product_variant.update_quantity(product.initial_quantity)
            product.is_ready_for_sale = True

    @api.depends("mpn")
    def _compute_reference_product(self) -> None:
        for product in self:
            if product.source == "standard" or not product.mpn:
                product.reference_product = False
                continue
            products = self.env["product.template"].search([("mpn", "!=", False), ("image_256", "!=", False)])
            product_mpns = product.get_list_of_mpns()
            matching_products = products.filtered(lambda p: any(mpn.lower() in p.mpn.lower() for mpn in product_mpns))
            latest_product = max(matching_products, key=lambda p: p.create_date, default=None)
            product.reference_product = latest_product

    @api.depends("motor_product_template_name", "dismantle_notes")
    def _compute_template_name_with_dismantle_notes(self) -> None:
        for product in self:
            product.template_name_with_dismantle_notes = (
                f"{product.motor_product_template_name}\n({product.dismantle_notes})"
                if product.dismantle_notes
                else product.motor_product_template_name
            )

    @api.depends("name", "motor_product_computed_name", "default_code")
    def _compute_display_name(self) -> None:
        for product in self:
            if isinstance(product.id, models.NewId):
                super()._compute_display_name()
                continue
            name = product.motor_product_computed_name if product.source == "motor" else product.name
            placeholder = "New Product"
            if name:
                product.display_name = f"[{product.default_code}] {name}"
            else:
                product.display_name = f"[{product.default_code}] {placeholder}"

    @api.depends(
        "motor.manufacturer.name",
        "motor_product_template.name",
        "mpn",
        "motor.year",
        "motor.horsepower",
        "motor_product_template.include_year_in_name",
        "motor_product_template.include_hp_in_name",
        "motor_product_template.include_model_in_name",
        "motor_product_template.include_oem_in_name",
    )
    def _compute_motor_product_computed_name(self) -> None:
        for product in self:
            if product.source != "motor":
                product.motor_product_computed_name = False
                continue

            name_parts = [
                product.motor.year if product.motor_product_template.include_year_in_name else None,
                product.motor.manufacturer.name if product.motor.manufacturer else None,
                (
                    product.motor.get_horsepower_formatted() if product.motor_product_template.include_hp_in_name else None),
                product.motor.stroke.name,
                "Outboard",
                product.motor_product_template.name,
                "OEM" if product.motor_product_template.include_oem_in_name else None,
            ]
            product.motor_product_computed_name = " ".join(str(part) for part in name_parts if part)

    @api.depends(
        "is_dismantled",
        "is_dismantled_qc",
        "is_cleaned",
        "is_cleaned_qc",
        "is_pictured",
        "is_pictured_qc",
        "is_scrap",
        "bin",
        "weight",
    )
    def _compute_ready_to_list(self) -> None:
        for product in self:
            product.is_ready_to_list = all(
                [
                    product.is_dismantled,
                    product.is_dismantled_qc,
                    product.is_cleaned,
                    product.is_cleaned_qc,
                    product.is_pictured,
                    product.is_pictured_qc,
                    product.bin,
                    product.weight,
                    not product.is_scrap,
                ]
            )

    def reset_name(self) -> None:
        for product in self:
            product._compute_motor_product_computed_name()
            product.name = product.motor_product_computed_name

    def replace_template_tags(self, templated_content: str) -> str:
        if not templated_content:
            return ""

        if not self.motor_product_template:
            return templated_content

        used_tags = re.findall(r"{(.*?)}", templated_content.lower())
        template_tags = self.motor_product_template.get_template_tags()
        values = {}

        for tag in used_tags:
            if tag not in template_tags:
                continue

            tag_value = template_tags.get(tag, tag)
            resolved_value = self._resolve_tag_value(tag_value) or ""
            values[tag] = str(resolved_value)

        return self._apply_tag_values(templated_content, values)

    def _resolve_tag_value(self, tag_value: str) -> str:
        if tag_value.startswith("tests."):
            parts = tag_value.split(".")
            if len(parts) < 2 or not parts[1].isdigit():
                return ""
            test_index = int(parts[1])
            test = self.motor.tests.filtered(lambda t: t.template.id == test_index)
            if not test:
                return ""
            test = test[0]
            if test.selection_result:
                return test.selection_result.display_value or test.selection_result.value
            return test.computed_result

        value = self.motor
        for field_part in tag_value.split("."):
            value = getattr(value, field_part, "")
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
        return str(value)

    @staticmethod
    def _apply_tag_values(content: str, values: dict[str, str]) -> str:
        for tag, value in values.items():
            content = content.replace(f"{{{tag}}}", value).replace("  ", " ")
        return content

    def create_repair_order(self) -> "odoo.values.ir_actions_act_window":
        self.ensure_one()
        self.is_listable = True
        company_partner_id = self.env.company.partner_id.id
        note = f"Tech Result '{self.tech_result.name}'<br/>" if self.tech_result else ""
        for test in self.motor.tests:
            relevant_conditions = self.motor_product_template.repair_by_tests.filtered(
                lambda c: c.conditional_test == test.template)
            for condition in relevant_conditions:
                if condition.is_condition_met(test.computed_result):
                    note += f"Test '{test.name}' failed: {test.computed_result}</br>"
                    break

        return {
            "type": "ir.actions.act_window",
            "name": "Create Repair Order",
            "res_model": "repair.order",
            "view_mode": "form",
            "context": {
                "default_partner_id": company_partner_id,
                "default_product_id": self.product_variant_id.id,
                "default_product_uom": self.uom_id.id,
                "default_location_id": self.property_stock_production.id,
                "repair_state_compute_timestamp": fields.Datetime.now(),
                "default_internal_notes": note,
            },
            "target": "new",
        }

    def action_open_repairs(self) -> "odoo.values.ir_actions_act_window":
        self.ensure_one()
        if not self.repairs:
            raise UserError("No repairs found.")

        domain = [("product_id", "in", self.product_variant_ids.ids)]
        return {
            "type": "ir.actions.act_window",
            "name": "Repair Orders",
            "res_model": "repair.order",
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }
