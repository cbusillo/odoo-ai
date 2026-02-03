from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MotorDismantleResult(models.Model):
    _name = "motor.dismantle.result"
    _order = "sequence"
    _description = "Motor Dismantle Result"

    sequence = fields.Integer(default=10, index=True)
    name = fields.Char(required=True)
    mark_for_repair = fields.Boolean(default=True)


class MotorProductTemplateCondition(models.Model):
    _name = "motor.product.template.condition"
    _description = "Motor Product Template Condition"
    _inherit = ["motor.test.condition.mixin"]

    excluded_template = fields.Many2one("motor.product.template", ondelete="cascade")
    repair_template = fields.Many2one("motor.product.template", ondelete="cascade")
    excluded_by_tests = fields.One2many("product.template", "motor_product_template", string="Excluded by Tests")


class MotorProductTemplate(models.Model):
    _name = "motor.product.template"
    _description = "Motor Product Template"
    _order = "sequence, id"

    name = fields.Char(required=True)

    strokes = fields.Many2many("motor.stroke")
    configurations = fields.Many2many("motor.configuration")
    manufacturers = fields.Many2many("product.manufacturer", domain=[("is_motor_manufacturer", "=", True)])
    excluded_by_parts = fields.Many2many("motor.part.template")
    excluded_by_tests = fields.One2many("motor.product.template.condition", "excluded_template")
    repair_by_tests = fields.One2many("motor.product.template.condition", "repair_template")
    repair_by_tech_results = fields.Many2many(
        "motor.dismantle.result",
        default=lambda self: self.env["motor.dismantle.result"].search([("mark_for_repair", "=", True)]).ids,
    )
    is_quantity_listing = fields.Boolean(default=False)
    include_year_in_name = fields.Boolean(default=True)
    include_hp_in_name = fields.Boolean(default=True, string="Include HP in Name")
    include_model_in_name = fields.Boolean(default=True)
    include_oem_in_name = fields.Boolean(default=True, string="Include OEM in Name")

    year_from = fields.Integer(help="Minimum year this template applies to (inclusive). Leave empty to include all older motors.")
    year_to = fields.Integer(help="Maximum year this template applies to (inclusive). Leave empty to include all newer motors.")
    year_range_display = fields.Char(string="Year Range", compute="_compute_year_range_display", store=False)

    part_type = fields.Many2one("product.type", index=True)
    initial_quantity = fields.Float()
    bin = fields.Char()
    weight = fields.Float()
    sequence = fields.Integer(default=10, index=True)
    website_description = fields.Html(string="HTML Description")

    @api.depends("year_from", "year_to")
    def _compute_year_range_display(self) -> None:
        for template in self:
            if template.year_from and template.year_to:
                template.year_range_display = f"{template.year_from} - {template.year_to}"
            elif template.year_from:
                template.year_range_display = f"{template.year_from} - Present"
            elif template.year_to:
                template.year_range_display = f"Up to {template.year_to}"
            else:
                template.year_range_display = "All Years"

    @api.constrains("year_from", "year_to")
    def _check_year_range(self) -> None:
        # Get valid years from motor model (now returns integers as keys)
        valid_years = [year for year, _ in self.env["motor"]._get_years()]
        min_year = min(valid_years)
        max_year = max(valid_years)

        for template in self:
            if template.year_from and template.year_from not in valid_years:
                raise ValidationError(f"Year From must be between {min_year} and {max_year}")

            if template.year_to and template.year_to not in valid_years:
                raise ValidationError(f"Year To must be between {min_year} and {max_year}")

            if template.year_from and template.year_to:
                if template.year_from > template.year_to:
                    raise ValidationError(f"Year From ({template.year_from}) cannot be greater than Year To ({template.year_to})")

    @api.onchange("year_from", "year_to")
    def _onchange_year_range(self) -> dict[str, dict[str, str]] | None:
        if self.year_from and self.year_to:
            if self.year_from > self.year_to:
                # Swap the values if from is greater than to
                self.year_from, self.year_to = self.year_to, self.year_from
                return {
                    "warning": {
                        "title": _("Years Swapped"),
                        "message": _("Year From was greater than Year To, so the values have been swapped."),
                    }
                }
        return None

    def _get_motors_for_template(self) -> "odoo.model.motor":
        self.ensure_one()
        domain = []

        if self.strokes:
            domain.append(("stroke", "in", self.strokes.ids))
        if self.configurations:
            domain.append(("configuration", "in", self.configurations.ids))
        if self.manufacturers:
            domain.append(("manufacturer", "in", self.manufacturers.ids))
        if self.year_from:
            domain.append(("year", ">=", self.year_from))
        if self.year_to:
            domain.append(("year", "<=", self.year_to))

        return self.env["motor"].search(domain)

    @api.model
    def get_template_tags_list(self) -> list[str]:
        tag_keys = list(self.get_template_tags().keys())
        tag_keys += ["mpn"]
        sorted_tags = sorted(tag_keys)
        return sorted_tags

    def get_template_tags(self) -> dict[str, str]:
        all_tags = self.get_template_tags_from_motor_model()
        all_tags.update(self.get_template_tags_from_test_tags())
        return all_tags

    def get_template_tags_from_test_tags(self) -> dict[str, str]:
        tests = self.env["motor.test.template"].search([("tag", "!=", "")])
        return {test.tag: test.tag_value for test in tests}

    def get_template_tags_from_motor_model(self) -> dict[str, str]:
        template_tags = {}
        fields_to_skip = ("uid", "stage", "is_")
        motor_model = self.env["motor"]
        for field_name, field in motor_model._fields.items():
            if any(skip in field_name for skip in fields_to_skip):
                continue
            if isinstance(field, (fields.Selection, fields.Selection, fields.Many2one, fields.Float, fields.Text)):
                template_tags[f"motor_{field_name}"] = field_name

        return template_tags
