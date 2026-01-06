from odoo import api, fields, models

from ..utils.constants import YES_NO_SELECTION


class MotorTestSection(models.Model):
    _name = "motor.test.section"
    _description = "Motor Test Section"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10, index=True)
    templates = fields.One2many("motor.test.template", "section")
    tests = fields.One2many("motor.test", "section")
    motor = fields.Many2one("motor", ondelete="restrict")


class MotorTestTemplate(models.Model):
    _name = "motor.test.template"
    _description = "Motor Test Template"
    _order = "sequence, id"
    _unique_tag = models.Constraint("unique(tag)", "The tag must be unique.")

    name = fields.Char("Test Name", required=True)
    tag = fields.Char()
    tag_value = fields.Char(compute="_compute_value")
    result_type = fields.Selection(
        [
            ("yes_no", "Yes/No"),
            ("numeric", "Numeric"),
            ("text", "Text"),
            ("selection", "Selection"),
            ("file", "File Upload"),
        ],
        string="Test Type",
        required=True,
    )
    selection_options = fields.Many2many("motor.test.selection")
    default_value = fields.Char()
    strokes = fields.Many2many("motor.stroke")
    manufacturers = fields.Many2many("product.manufacturer", domain="[('is_motor_manufacturer', '=', True)]")
    configurations = fields.Many2many("motor.configuration")
    conditions = fields.One2many(
        "motor.test.template.condition",
        "template",
    )
    conditional_tests = fields.One2many(
        "motor.test.template.condition",
        "conditional_test",
    )
    missing_parts = fields.Many2many(
        "motor.part.template",
        string="Missing Parts",
        domain=lambda self: [("hidden_tests", "in", self.ids)],
    )
    stage = fields.Selection(
        [
            ("basic", "Basic Testing"),
            ("extended", "Extended Testing"),
        ],
        required=True,
    )
    section = fields.Many2one("motor.test.section", required=True)
    sequence = fields.Integer(default=10, index=True)

    def _compute_value(self) -> None:
        for test in self:
            if test.tag:
                test.tag_value = f"tests.{test.id}"
            else:
                test.tag_value = ""


class MotorTestTemplateCondition(models.Model):
    _name = "motor.test.template.condition"
    _description = "Motor Test Template Condition"
    _inherit = ["motor.test.condition.mixin"]

    template = fields.Many2one("motor.test.template", ondelete="cascade")

    action_type = fields.Selection(
        [
            ("show", "Show Test"),
            ("hide", "Hide Test"),
        ],
        required=True,
    )


class MotorTestSelection(models.Model):
    _name = "motor.test.selection"
    _description = "Motor Test Selection"
    _order = "sequence"
    _unique_selection_value = models.Constraint("unique(value)", "The value must be unique.")

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10, index=True)
    value = fields.Char(required=True)
    display_value = fields.Char()
    templates = fields.Many2many("motor.test.template", ondelete="cascade")

    def __str__(self) -> str:
        return self.name if self.name else ""


class MotorTest(models.Model):
    _name = "motor.test"
    _description = "Motor Test Instance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "section_sequence, sequence, id"

    name = fields.Char(related="template.name")
    motor = fields.Many2one("motor", ondelete="cascade", required=True)
    template = fields.Many2one("motor.test.template", string="Test Template", ondelete="restrict")
    sequence = fields.Integer(string="Test Sequence", related="template.sequence", index=True, store=True)
    result_type = fields.Selection(related="template.result_type")
    section = fields.Many2one(related="template.section")
    section_sequence = fields.Integer(string="Section Sequence", related="section.sequence", index=True, store=True)

    yes_no_result = fields.Selection(YES_NO_SELECTION)
    selection_options = fields.Many2many(related="template.selection_options")

    selection_result = fields.Many2one("motor.test.selection", domain="[('id', 'in', selection_options)]")
    selection_result_value = fields.Char(related="selection_result.value")

    numeric_result = fields.Float()
    text_result = fields.Text()
    file_result = fields.Binary()
    computed_result = fields.Char(compute="_compute_result", store=True, tracking=True)
    default_value = fields.Char(related="template.default_value")
    is_applicable = fields.Boolean(compute="_compute_is_applicable", store=True)

    strokes = fields.Many2many(related="template.strokes")
    manufacturers = fields.Many2many(related="template.manufacturers")
    configurations = fields.Many2many(related="template.configurations")
    conditions = fields.One2many(
        "motor.test.template.condition",
        related="template.conditions",
    )
    conditional_tests = fields.One2many(
        "motor.test.template.condition",
        related="template.conditional_tests",
    )

    def write(self, vals: "odoo.values.motor_test") -> bool:
        result = super().write(vals)
        if self.motor and not self.env.context.get("tracking_motor_test"):
            message_text = f"Test '{self.name}' updated"
            if "computed_result" in vals or any(key.endswith("_result") for key in vals):
                message_text = f"Test '{self.name}' result updated to: {self.computed_result}"
            self.motor.message_post(body=message_text, message_type="comment", subtype_xmlid="mail.mt_note")
        return result

    @api.depends("yes_no_result", "numeric_result", "text_result", "selection_result", "file_result")
    def _compute_result(self) -> None:
        for test in self:
            if test.result_type == "yes_no":
                test.computed_result = dict(YES_NO_SELECTION).get(test.yes_no_result) or ""
            elif test.result_type == "numeric":
                test.computed_result = test.numeric_result or ""
            elif test.result_type == "text":
                test.computed_result = test.text_result
            elif test.result_type == "selection":
                test.computed_result = (
                    test.selection_result.display_value
                    or test.selection_result_value
                    or ""
                )
            elif test.result_type == "file":
                test.computed_result = "File Uploaded" if test.file_result else ""

    @api.depends(
        "motor.configuration",
        "motor.manufacturer",
        "motor.parts.is_missing",
        "motor.parts.hidden_tests",
        "motor.tests.computed_result",
        "configurations",
        "manufacturers",
        "conditional_tests",
    )
    def _compute_is_applicable(self) -> None:
        for test in self:
            test.is_applicable = False
            if test.configurations and test.motor.configuration not in test.configurations:
                continue
            if test.manufacturers and test.motor.manufacturer not in test.manufacturers:
                continue

            if any(part.is_missing and test.template.id in part.hidden_tests.ids for part in test.motor.parts):
                continue

            motor_id = test.motor.id or test.motor._origin.id

            if test.conditional_tests and not all(
                conditional_test.is_condition_met(
                    self.env["motor.test"]
                    .search(
                        [
                            ("template.id", "=", conditional_test.template.id),
                            ("motor.id", "=", motor_id),
                        ],
                        limit=1,
                    )
                    .computed_result
                )
                for conditional_test in test.conditional_tests
            ):
                continue

            test.is_applicable = True
