import logging
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "label.mixin", "notification.manager.mixin"]

    motor = fields.Many2one("motor", ondelete="restrict", readonly=True, index=True)
    motor_tests = fields.One2many("motor.test", related="motor.tests")

    motor_product_template = fields.Many2one("motor.product.template", ondelete="restrict", readonly=True)
    motor_product_template_name = fields.Char(related="motor_product_template.name", string="Template Name")
    motor_product_computed_name = fields.Char(compute="_compute_motor_product_computed_name", store=True)
    is_qty_listing = fields.Boolean(related="motor_product_template.is_quantity_listing")

    tech_result = fields.Many2one(comodel_name="motor.dismantle.result", ondelete="restrict", tracking=True)
    dismantle_notes = fields.Text()
    template_name_with_dismantle_notes = fields.Char(compute="_compute_template_name_with_dismantle_notes", store=False)

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
    is_ready_for_sale = fields.Boolean(tracking=True, index=True, default=True)
    source = fields.Selection(
        [("import", "Import Product"), ("motor", "Motor Product"), ("shopify", "Shopify Product"), ("standard", "Standard Product")],
        default="standard",
        required=False,
        index=True,
    )
    bin = fields.Char(index=True)
    initial_quantity = fields.Float(string="Quantity", index=True)
    reference_product = fields.Many2one("product.template", compute="_compute_reference_product", store=True, index=True)
    name_with_tags_length = fields.Integer(compute="_compute_name_with_tags_length")
    images = fields.One2many("product.image", "product_tmpl_id")
    image_count = fields.Integer(compute="_compute_image_count", store=True)
    image_icon = fields.Binary(related="images.image_1920", string="Image Icon")
    image_1920 = fields.Image(compute="_compute_image_1920", inverse="_inverse_image_1920", store=True)
    length = fields.Integer()
    width = fields.Integer()
    height = fields.Integer()
    has_recent_messages = fields.Boolean(compute="_compute_has_recent_messages", store=True)
    is_price_or_cost_missing = fields.Boolean(compute="_compute_is_price_or_cost_missing", store=True, index=True)

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

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.product_template"]) -> "odoo.model.product_template":
        for vals in vals_list:
            if vals.get("motor") or vals.get("motor_product_template"):
                if "source" in self._fields and not vals.get("source"):
                    vals["source"] = "motor"
                if "is_ready_for_sale" in self._fields and "is_ready_for_sale" not in vals:
                    vals["is_ready_for_sale"] = False

        products = super().create(vals_list)
        for product in products:
            if product.motor_product_template:
                product._compute_motor_product_computed_name()
                if product.motor_product_computed_name:
                    product.name = product.motor_product_computed_name

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

            if "images" in self._fields and "is_pictured" in vals_to_write and vals_to_write["is_pictured"]:
                if not product.images:
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

            if "is_dismantled" in vals_to_write and vals_to_write["is_dismantled"] and product.motor:
                message_text = f"Product '{product.motor_product_template_name}' dismantled"
                product.motor.message_post(body=message_text, message_type="comment", subtype_xmlid="mail.mt_note")

            if "tech_result" in vals_to_write and product.motor:
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

            write_results.append(super(ProductTemplate, product).write(vals_to_write))

            if "image_count" in self._fields and product.image_count < 1 and (product.is_pictured or product.is_pictured_qc):
                product.is_pictured = False
                product.is_pictured_qc = False

            if product.motor and any(field in vals_to_write for field in ui_refresh_fields):
                product.motor.notify_changes()

        return all(write_results)

    def _track_template(self, changes: set[str]) -> dict[str, tuple[str, dict]]:
        self.ensure_one()
        result = super()._track_template(changes)
        if "repair_state" not in changes:
            return result
        template = self.env.ref(
            "marine_motors.mail_template_repair_state_change",
            raise_if_not_found=False,
        )
        if not template:
            if not self.env.context.get("install_mode"):
                _logger.warning("Missing mail template marine_motors.mail_template_repair_state_change")
            return result
        result["repair_state"] = (
            "marine_motors.mail_template_repair_state_change",
            {},
        )
        return result

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
            if isinstance(product.id, api.NewId):
                super()._compute_display_name()
                continue
            name = product.motor_product_computed_name or product.name
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
            if not product.motor_product_template or not product.motor:
                product.motor_product_computed_name = False
                continue

            name_parts = [
                product.motor.year if product.motor_product_template.include_year_in_name else None,
                product.motor.manufacturer.name if product.motor.manufacturer else None,
                (product.motor.get_horsepower_formatted() if product.motor_product_template.include_hp_in_name else None),
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
            bin_value = getattr(product, "bin", None)
            product.is_ready_to_list = all(
                [
                    product.is_dismantled,
                    product.is_dismantled_qc,
                    product.is_cleaned,
                    product.is_cleaned_qc,
                    product.is_pictured,
                    product.is_pictured_qc,
                    bin_value,
                    product.weight,
                    not product.is_scrap,
                ]
            )

    @api.depends("mpn")
    def _compute_reference_product(self) -> None:
        for product in self:
            source_value = getattr(product, "source", None)
            if source_value == "standard" or not product.mpn:
                product.reference_product = False
                continue
            products = self.env["product.template"].search([("mpn", "!=", False), ("image_256", "!=", False)])
            product_mpns = product.get_list_of_mpns()
            matching_products = products.filtered(lambda p: any(mpn.lower() in p.mpn.lower() for mpn in product_mpns))
            latest_product = max(matching_products, key=lambda p: p.create_date, default=None)
            product.reference_product = latest_product

    def _compute_name_with_tags_length(self) -> None:
        for product in self:
            name = product.replace_template_tags(product.name or "")
            name = name.replace("{mpn}", product.first_mpn)
            product.name_with_tags_length = len(name)

    @api.depends("product_template_image_ids")
    def _compute_image_1920(self) -> None:
        for product in self:
            first_image = product.product_template_image_ids[:1]
            product.image_1920 = first_image.image_1920 if first_image else False

    def _inverse_image_1920(self) -> None:
        for product in self:
            first_image = product.product_template_image_ids[:1]
            if first_image:
                first_image.write({"image_1920": product.image_1920})
            elif product.image_1920:
                self.env["product.image"].create(
                    {
                        "product_tmpl_id": product.id,
                        "image_1920": product.image_1920,
                        "name": f"{product.name}_image",
                    }
                )

    @api.depends("images.image_1920")
    def _compute_image_count(self) -> None:
        for product in self:
            image_ids = product.images.ids
            if not image_ids:
                product.image_count = 0
                continue
            product.image_count = self.env["ir.attachment"].search_count(
                [
                    ("res_model", "=", "product.image"),
                    ("res_id", "in", image_ids),
                    ("res_field", "=", "image_1920"),
                    ("file_size", ">", 0),
                ]
            )

    @api.depends("list_price", "standard_price")
    def _compute_is_price_or_cost_missing(self) -> None:
        for product in self:
            product.is_price_or_cost_missing = not product.list_price or not product.standard_price

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

    @api.constrains("length", "width", "height")
    def _check_dimension_values(self) -> None:
        for product in self:
            dimension_values = [product.length, product.width, product.height]
            for dimension in dimension_values:
                if dimension and len(str(abs(int(dimension)))) > 2:
                    raise ValidationError("Dimensions cannot exceed 2 digits.")

    def reset_name(self) -> None:
        for product in self:
            product._compute_motor_product_computed_name()
            product.name = product.motor_product_computed_name

    def enable_ready_for_sale(self) -> None:
        products_to_enable = self.filtered(lambda p: p.is_ready_to_list or p.source == "import")
        if not products_to_enable:
            raise UserError("No products are ready to sell.")
        products_to_enable.write({"is_ready_for_sale": True})

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
                f"{product.motor.motor_number if product.motor else '       '}",
                product.condition.name if product.condition else "",
            ]
            is_ready_for_sale = getattr(product, "is_ready_for_sale", False)
            quantity_field_name = "qty_available" if is_ready_for_sale else "initial_quantity"
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

    def create_repair_order(self) -> "odoo.values.ir_actions_act_window":
        self.ensure_one()
        self.is_listable = True
        company_partner_id = self.env.company.partner_id.id
        note = f"Tech Result '{self.tech_result.name}'<br/>" if self.tech_result else ""
        for test in self.motor.tests:
            relevant_conditions = self.motor_product_template.repair_by_tests.filtered(lambda c: c.conditional_test == test.template)
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
