import base64
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Self

import qrcode
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..utils import constants


class MotorStage(models.Model):
    _name = "motor.stage"
    _description = "Motor Stage"
    _order = "sequence"

    name = fields.Char(required=True, index=True)
    motors = fields.One2many("motor", "stage")
    sequence = fields.Integer(default=10, index=True)
    fold_by_default = fields.Boolean(default=False)
    fold = fields.Boolean(compute="_compute_fold")

    @api.depends("fold_by_default")
    def _compute_fold(self) -> None:
        user_folded_stages = self.env.user.folded_motor_stages
        for stage in self:
            stage.fold = stage.id in user_folded_stages.ids or stage.fold_by_default


class MotorTag(models.Model):
    _name = "motor.tag"
    _description = "Motor Tag"

    name = fields.Char(required=True)
    color = fields.Integer(string="Color Index")

    _name_uniq = models.Constraint("unique (name)", "Tag name already exists!")


class Motor(models.Model):
    _name = "motor"
    _rec_name = "motor_number"
    _inherit = ["label.mixin", "mail.tracking.duration.mixin", "mail.activity.mixin"]
    _description = "Motor Information"
    _track_duration_field = "stage"
    _order = "motor_number desc"
    _motor_number_uniq = models.Constraint("unique (motor_number)", "Motor number already exists!")

    stage = fields.Many2one(
        "motor.stage",
        tracking=True,
        group_expand="_read_group_stages",
        default=lambda self: self.env["motor.stage"].search([("name", "=", "Checkin")], limit=1),
    )
    stage_name = fields.Char(related="stage.name")

    @api.model
    def _read_group_stages(self, *_args: object, **_kwargs: object) -> "odoo.model.motor_stage":
        all_stages = self.env["motor.stage"].search([])
        self.env["motor"].search([("stage", "=", False), ("active", "in", [True, False])]).write(
            {"stage": all_stages.search([("name", "=", "Checkin")], limit=1).id}
        )
        return all_stages

    priority = fields.Selection(
        [
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
        ],
        default="1",
        index=True,
        tracking=True,
    )
    date_deadline = fields.Date(string="Deadline", index=True, tracking=True)
    date_last_stage_update = fields.Datetime(
        string="Last Stage Update",
        index=True,
        copy=False,
        readonly=True,
    )

    tags = fields.Many2many("motor.tag", string="Tags")
    product_count = fields.Integer(compute="_compute_product_count")
    completed_test_count = fields.Integer(compute="_compute_completed_test_count")
    applicable_test_count = fields.Integer(compute="_compute_applicable_test_count")

    def _compute_product_count(self) -> None:
        for motor in self:
            motor.product_count = len(motor.products)

    def _compute_completed_test_count(self) -> None:
        for motor in self:
            motor.completed_test_count = len(motor.tests.filtered(lambda test: test.computed_result and test.is_applicable))

    def _compute_applicable_test_count(self) -> None:
        for motor in self:
            motor.applicable_test_count = len(motor.tests.filtered(lambda test: test.is_applicable))

    def action_view_products(self) -> "odoo.values.ir_actions_act_window":
        return {
            "name": "Motor Products",
            "type": "ir.actions.act_window",
            "res_model": "product.template",
            "view_mode": "list,form",
            "domain": [("motor", "=", self.id)],
            "context": {"default_motor": self.id},
            "target": "new",
        }

    def action_view_tests(self) -> "odoo.values.ir_actions_act_window":
        return {
            "name": "Motor Tests",
            "type": "ir.actions.act_window",
            "res_model": "motor.test",
            "view_mode": "list,form",
            "domain": [("motor", "=", self.id)],
            "context": {"default_motor": self.id},
        }

    active = fields.Boolean(default=True, index=True)
    motor_number = fields.Char(index=True)
    location = fields.Char()
    vendor = fields.Many2one("res.partner")
    lot_id = fields.Char(size=5)
    manufacturer = fields.Many2one(
        "product.manufacturer", domain="[('is_motor_manufacturer', '=', True)]", required=True, index=True
    )
    horsepower = fields.Float(digits=(3, 1), string="HP", required=True)
    horsepower_formatted = fields.Char(compute="_compute_horsepower_formatted")
    stroke = fields.Many2one("motor.stroke", required=True, index=True)
    configuration = fields.Many2one("motor.configuration", required=True, index=True)
    model = fields.Char()
    sub_model = fields.Char()
    serial_number = fields.Char()

    @api.model
    def _get_years(self) -> list[tuple[int, str]]:
        return [(year, str(year)) for year in range(fields.Date.today().year + 1, 1960, -1)]

    year = fields.Selection(_get_years, string="Model Year", index=True)
    color = fields.Many2one("product.color", domain="[('applicable_tags.name', '=', 'Motors')]")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id, required=True)
    cost = fields.Monetary(currency_field="currency_id")
    price = fields.Monetary(
        compute="_compute_price_of_motor",
        store=True,
        currency_field="currency_id",
        help="Total price of all products of a motor.  Adds the price multiplied by quantity of all products that are \
        listable.  This is recomputed when a product's listable status, initial_quantity, or price is changed.  It \
        will also be recomputed when the motor cost is changed.",
    )

    # from tests
    hours = fields.Float(compute="_compute_hours")
    shaft_length = fields.Char(compute="_compute_shaft_length")

    is_tag_readable = fields.Selection(constants.YES_NO_SELECTION, default=constants.YES)
    notes = fields.Text(tracking=True)
    has_notes = fields.Boolean(compute="_compute_has_notes", store=True)
    images = fields.One2many("motor.image", "motor")
    image_count = fields.Integer(compute="_compute_image_count")
    image_icon = fields.Binary(compute="_compute_icon", store=True)
    parts = fields.One2many("motor.part", "motor")
    missing_parts = fields.One2many("motor.part", "motor", domain=[("is_missing", "=", True)])
    missing_parts_names = fields.Char(compute="_compute_missing_parts_names", store=True)
    tests = fields.One2many("motor.test", "motor")
    test_sections = fields.One2many("motor.test.section", "motor")
    basic_tests = fields.One2many("motor.test", "motor", domain=[("template.stage", "=", "basic")])
    extended_tests = fields.One2many("motor.test", "motor", domain=[("template.stage", "=", "extended")])

    cylinders = fields.One2many("motor.cylinder", "motor")

    hide_compression_page = fields.Boolean(compute="_compute_hide_compression_page", store=True)
    products = fields.One2many("product.template", "motor")
    products_not_enabled = fields.One2many("product.template", "motor", domain=[("is_ready_for_sale", "=", False)])
    products_with_reference_product = fields.Many2many(
        "product.template",
        "motor_product_with_reference_product_rel",
        "motor_id",
        "product_id",
        compute="_compute_products_with_reference",
        store=True,
    )

    products_to_dismantle = fields.One2many(
        "product.template",
        "motor",
        domain=[("is_ready_for_sale", "=", False), ("is_listable", "=", True)],
    )

    products_to_clean = fields.One2many(
        "product.template",
        "motor",
        domain=[
            ("repair_state", "!=", "in_repair"),
            ("is_ready_for_sale", "=", False),
            ("is_listable", "=", True),
            ("is_dismantled", "=", True),
            ("is_dismantled_qc", "=", True),
        ],
    )

    products_to_picture = fields.One2many(
        "product.template",
        "motor",
        domain=[
            ("repair_state", "!=", "in_repair"),
            ("is_ready_for_sale", "=", False),
            ("is_listable", "=", True),
            ("is_dismantled", "=", True),
            ("is_dismantled_qc", "=", True),
            ("is_cleaned", "=", True),
            ("is_cleaned_qc", "=", True),
        ],
    )

    products_to_stock = fields.One2many(
        "product.template",
        "motor",
        domain=[
            ("repair_state", "!=", "in_repair"),
            ("is_ready_for_sale", "=", False),
            ("is_listable", "=", True),
            ("is_dismantled", "=", True),
            ("is_dismantled_qc", "=", True),
            ("is_cleaned", "=", True),
            ("is_cleaned_qc", "=", True),
            ("is_pictured", "=", True),
            ("is_pictured_qc", "=", True),
        ],
    )

    product_repair_states_with_icons = fields.Json(compute="_compute_product_repair_states_with_icons", store=True)

    def _compute_product_repair_states_with_icons(self) -> None:
        state_mapping = {
            "may_need_repair": {"icon": "fa-exclamation-triangle", "title": "May Need Repair", "color": "warning"},
            "in_repair": {"icon": "fa-cog", "title": "In Repair", "color": "danger"},
            "repaired": {"icon": "fa-check-circle", "title": "Repaired", "color": "success"},
            "cancelled": {"icon": "fa-times-circle", "title": "Cancelled Repair", "color": "muted"},
        }
        for motor in self:
            states = set(motor.products.mapped("repair_state")) - {"none"}
            states_with_icons = [{"id": state, **state_mapping[state]} for state in states if state in state_mapping]
            motor.product_repair_states_with_icons = states_with_icons

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.motor"]) -> Self:
        vals_list = [self._sanitize_vals(vals) for vals in vals_list]

        motors = super().create(vals_list)
        for motor in motors:
            if motor.id > 999999:
                raise ValidationError(self.env._("Motor number cannot exceed 999999."))
            motor.motor_number = f"M-{str(motor.id).zfill(6)}"
            motor._create_default_images(motor)
            motor._compute_compression()
            motor._create_motor_parts()
            motor._create_motor_tests()

        return motors

    def write(self, vals: "odoo.values.motor") -> bool:
        vals = self._sanitize_vals(vals)
        if "stage" in vals:
            vals["date_last_stage_update"] = fields.Datetime.now()

        result = super().write(vals)
        if "configuration" in vals:
            self._compute_compression()

        return result

    @api.depends("products_not_enabled.reference_product", "products_not_enabled.reference_product.image_256")
    def _compute_products_with_reference(self) -> None:
        for motor in self:
            reference_products = motor.products_not_enabled.filtered(lambda p: p.reference_product and p.reference_product.image_256)

            if reference_products != motor.products_with_reference_product:
                motor.products_with_reference_product = reference_products

    def _compute_image_count(self) -> None:
        for motor in self:
            motor.image_count = len([image for image in motor.images if image.image_1920])

    def _compute_missing_parts_names(self) -> None:
        for motor in self:
            missing_parts_names = ", ".join(part.name for part in motor.missing_parts if part.name)
            motor.missing_parts_names = missing_parts_names

    def _compute_shaft_length(self) -> None:
        for motor in self:
            shaft_length = motor.tests.filtered(lambda t: "shaft" in t.template.name.lower() and "length" in t.template.name.lower())
            motor.shaft_length = shaft_length.selection_result if shaft_length else ""

    def _compute_hours(self) -> None:
        for motor in self:
            hours = motor.tests.filtered(lambda t: "engine" in t.template.name.lower() and "hours" in t.template.name.lower())
            motor.hours = hours.numeric_result if hours else 0

    @api.depends("notes")
    def _compute_has_notes(self) -> None:
        for motor in self:
            motor.has_notes = bool(motor.notes)

    @api.depends("images.image_128")
    def _compute_icon(self) -> None:
        for motor in self:
            motor.image_icon = next((image.image_128 for image in motor.images if image.image_128), False)

    @api.depends("horsepower")
    def _compute_horsepower_formatted(self) -> None:
        for motor in self:
            motor.horsepower_formatted = motor.get_horsepower_formatted()

    @api.depends("motor_number", "manufacturer", "model", "year", "serial_number", "horsepower")
    def _compute_display_name(self) -> None:
        for motor in self:
            serial_number = f" - {motor.serial_number}" if motor.serial_number else None

            name_parts = [
                motor.motor_number,
                motor.year,
                motor.manufacturer.name,
                motor.get_horsepower_formatted(),
                motor.model,
                serial_number,
            ]
            name = " ".join(str(part) for part in name_parts if part)

            if name:
                motor.display_name = name
            else:
                motor.display_name = "New Motor"

    @api.depends("parts.is_missing", "parts.template.hide_compression_page")
    def _compute_hide_compression_page(self) -> None:
        for motor in self:
            hide_parts = motor.parts.filtered(lambda p: p.is_missing and p.template.hide_compression_page)
            motor.hide_compression_page = bool(hide_parts)

    def set_all_cylinders_untestable(self) -> None:
        for motor in self:
            for cylinder in motor.cylinders:
                cylinder.is_untestable = True

    def generate_qr_code(self) -> str:
        qr_code = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=20,
        )
        qr_code.add_data(self.motor_number)
        qr_code.make()

        qr_image = qr_code.make_image(fill_color="black", back_color="white")

        with BytesIO() as qr_image_buffer:
            qr_image.save(qr_image_buffer)
            qr_image_base64 = base64.b64encode(qr_image_buffer.getvalue()).decode()

        return qr_image_base64

    def get_horsepower_formatted(self) -> str:
        if not self.horsepower:
            return ""

        if self.horsepower.is_integer():
            return f"{int(self.horsepower)} HP"
        else:
            return f"{self.horsepower} HP"

    @api.constrains("horsepower")
    def _check_horsepower(self) -> None:
        for motor in self:
            if motor.horsepower < 0.0 or motor.horsepower > 600.0:
                raise ValidationError(self.env._("Horsepower must be between 0 and 600."))

    @api.constrains("location")
    def _check_unique_location(self) -> None:
        for motor in self:
            if not motor.location:
                continue
            existing_motor = self.search([("location", "=", motor.location), ("id", "!=", motor.id)], limit=1)
            if existing_motor:
                raise ValidationError(
                    self.env._(f"Motor {existing_motor.motor_number} with location '{motor.location}' already exists.")
                )

    @staticmethod
    def _sanitize_vals(vals: "odoo.values.motor") -> "odoo.values.motor":
        if "model" in vals and vals["model"]:
            vals["model"] = vals["model"].upper()
        if "serial_number" in vals and vals["serial_number"]:
            vals["serial_number"] = vals["serial_number"].upper()
        return vals

    def _create_motor_tests(self) -> None:
        test_templates = self.env["motor.test.template"].search([])
        test_vals = []
        for template in test_templates:
            test_vals.append(
                {
                    "motor": self.id,
                    "template": template.id,
                }
            )
        if test_vals:
            self.env["motor.test"].create(test_vals)

    def _create_motor_parts(self) -> None:
        part_templates = self.env["motor.part.template"].search([])
        part_vals = []
        for template in part_templates:
            part_vals.append(
                {
                    "motor": self.id,
                    "template": template.id,
                }
            )
        if part_vals:
            self.env["motor.part"].create(part_vals)

    @staticmethod
    def _check_product_conditions(
        motor: "odoo.model.motor",
        conditions: "odoo.model.motor_product_template_condition",
    ) -> bool:
        for test in motor.tests:
            relevant_conditions = conditions.filtered(lambda c: c.conditional_test == test.template)
            if any(cond.is_condition_met(test.computed_result) for cond in relevant_conditions):
                return True
        return False

    @staticmethod
    def _should_exclude_product(motor: "odoo.model.motor", product_template: "odoo.model.motor_product_template") -> bool:
        return motor._check_product_conditions(motor, product_template.excluded_by_tests)

    @staticmethod
    def _should_repair_product(motor: "odoo.model.motor", product_template: "odoo.model.motor_product_template") -> bool:
        return motor._check_product_conditions(motor, product_template.repair_by_tests)

    def create_motor_products(self) -> None:
        product_templates = self.env["motor.product.template"].search([])

        for motor in self:
            missing_fields = []
            if not motor.cost:
                missing_fields.append("Cost")
            if not motor.horsepower:
                missing_fields.append("Horsepower")
            if not motor.year:
                missing_fields.append("Year")
            if not motor.model:
                missing_fields.append("Model")

            if missing_fields:
                raise UserError(self.env._(f"Motor is missing required fields: {', '.join(missing_fields)}"))

            current_product_ids = set(motor.products.ids)

            for product_template in product_templates:
                if product_template.strokes and motor.stroke not in product_template.strokes:
                    continue
                if product_template.configurations and motor.configuration not in product_template.configurations:
                    continue
                if product_template.manufacturers and motor.manufacturer not in product_template.manufacturers:
                    continue

                if motor.year:
                    if product_template.year_from and int(motor.year) < product_template.year_from:
                        continue
                    if product_template.year_to and int(motor.year) > product_template.year_to:
                        continue

                if any(part.template.id in product_template.excluded_by_parts.ids and part.is_missing for part in motor.parts):
                    continue

                if self._should_exclude_product(motor, product_template):
                    continue

                existing_product = motor.products.filtered(lambda p: p.motor_product_template == product_template)

                if existing_product:
                    current_product_ids.discard(existing_product.id)
                else:
                    condition_id = self.env.ref("product_metadata.product_condition_used").id
                    product_vals = {
                        "name": product_template.name,
                        "motor": motor.id,
                        "motor_product_template": product_template.id,
                        "initial_quantity": product_template.initial_quantity or 1,
                        "bin": product_template.bin,
                        "weight": product_template.weight,
                        "condition": condition_id,
                        "manufacturer": motor.manufacturer.id,
                        "website_description": product_template.website_description,
                        "is_ready_for_sale": False,
                        "part_type": product_template.part_type.id,
                        "type": "consu",
                        "is_storable": True,
                        "sequence": product_template.sequence,
                    }
                    if "source" in self.env["product.template"]._fields:
                        product_vals["source"] = "motor"
                    motor.products.create([product_vals])

            if current_product_ids:
                motor.products.filtered(lambda p: p.id in current_product_ids).unlink()

    def _get_cylinder_count(self) -> int:
        match = re.search(r"\d+", self.configuration.name)
        if match:
            return int(match.group())
        return 0

    def _compute_compression(self) -> None:
        for motor in self:
            desired_cylinders = motor._get_cylinder_count()
            current_cylinders = motor.cylinders.mapped("cylinder_number")

            excessive_cylinders = motor.cylinders.filtered(lambda x: x.cylinder_number > desired_cylinders)
            if excessive_cylinders:
                excessive_cylinders.unlink()

            # Add missing cylinders
            existing_cylinder_numbers = set(current_cylinders)
            for i in range(1, desired_cylinders + 1):
                if i not in existing_cylinder_numbers:
                    self.cylinders.create(
                        [
                            {
                                "motor": motor.id,
                                "cylinder_number": i,
                                "compression_psi": 0,
                            }
                        ]
                    )

    def _create_default_images(self, motor: Self) -> None:
        image_names = constants.MOTOR_IMAGE_NAME_AND_ORDER
        for name in image_names:
            self.images.create(
                [
                    {
                        "motor": motor.id,
                        "name": name,
                    }
                ]
            )

    def download_zip_of_images(self) -> dict[str, str]:
        temp_path = Path(tempfile.mkdtemp())
        zip_path = temp_path / f"{self.motor_number} {datetime.now().strftime('%Y-%m-%d %H-%M')}.zip"
        with zipfile.ZipFile(zip_path, "w") as zip_file:
            for motor in self:
                for image in motor.images:
                    if not image.image_1920:
                        continue
                    filename = f"{motor.motor_number} {image.name}.jpg"
                    file_path = temp_path / filename
                    with open(file_path, "wb") as image_file:
                        image_file.write(base64.b64decode(image.image_1920))
                    zip_file.write(file_path, filename)
                    file_path.unlink()

        with open(zip_path, "rb") as zip_file:
            zip_data = base64.b64encode(zip_file.read())

        attachment = self.env["ir.attachment"].create(
            [
                {
                    "name": zip_path.name,
                    "datas": zip_data,
                    "type": "binary",
                    "mimetype": "application/zip",
                }
            ]
        )

        download_url = f"/odoo/binary/download_single?attachment_id={attachment.id}"
        shutil.rmtree(temp_path)

        return {
            "type": "ir.actions.act_url",
            "url": download_url,
            "target": "self",
        }

    @api.depends("products.is_listable", "products.list_price", "products.initial_quantity", "cost")
    def _compute_price_of_motor(self) -> None:
        for motor in self:
            products = motor.products.filtered(lambda p: p.is_listable and p.initial_quantity > 0)
            self.price = sum(record.list_price * record.initial_quantity for record in products)

    def apply_cost(self) -> None:
        for motor in self:
            products = self.products.filtered(lambda p: p.is_listable and p.initial_quantity > 0)

            for product in products:
                cost_proportion = (product.list_price * product.initial_quantity) / motor.price if motor.price else 0
                product.standard_price = (cost_proportion * self.cost) / product.initial_quantity

    def enable_ready_for_sale(self) -> None:
        self.products_not_enabled.enable_ready_for_sale()

    def print_motor_product_labels(self) -> None:
        products = self.products.filtered(lambda p: p.is_listable and p.initial_quantity > 0)
        if not products:
            raise UserError(self.env._("No products to print labels for."))

        products.print_product_labels(use_available_qty=True)

    def print_motor_pull_list(self) -> None:
        products = self.products.filtered(lambda p: p.is_listable and p.initial_quantity > 0)
        if not products:
            raise UserError(self.env._("No products to print pull list for."))

        report_name = "marine_motors.report_motorproductpulllist"
        report_object = self.env["ir.actions.report"]._get_report_from_name(report_name)
        pdf_data, _type = report_object._render_qweb_pdf(report_name, res_ids=products.ids)

        self._print_labels(pdf_data, odoo_job_type="pull_list", job_name="Motor Pull List", copies=2)

    def notify_changes(self) -> None:
        self.ensure_one()
        channel = f"motor_{self.id}"
        message = {
            "type": "motor_product_update",
        }
        self.env["bus.bus"]._sendone(channel, "notification", message)

    def print_motor_labels(self, printer_job_type: str = "motor_label") -> None:
        for motor in self:
            if not motor.horsepower:
                raise UserError(self.env._("Motor is missing HP."))
            report_name = "marine_motors.report_motortemplatelabel4x2noprice"
            report_object = self.env["ir.actions.report"]._get_report_from_name(report_name)
            pdf_data, _ = report_object._render_qweb_pdf(report_name, res_ids=motor.ids)

            motor._print_labels(pdf_data, odoo_job_type=printer_job_type, job_name="Motor Label")
            motor.message_post(body="Motor label printed")
