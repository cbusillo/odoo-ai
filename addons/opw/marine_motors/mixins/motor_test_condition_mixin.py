from odoo import models, fields, exceptions


class MotorTestConditionMixin(models.AbstractModel):
    _name = "motor.test.condition.mixin"
    _description = "Motor Test Condition Mixin"

    conditional_test = fields.Many2one("motor.test.template", ondelete="cascade", required=True)
    condition_value = fields.Char(required=True)
    conditional_operator = fields.Selection(
        [
            (">", "Greater Than"),
            ("<", "Less Than"),
            (">=", "Greater Than or Equal To"),
            ("<=", "Less Than or Equal To"),
            ("=", "Equal To"),
            ("!=", "Not Equal To"),
        ],
        required=True,
        default="=",
    )

    def is_condition_met(self, test_value: str | float) -> bool:
        self.ensure_one()
        if not self.conditional_operator or not self.condition_value:
            return False

        if self.conditional_test.result_type == "selection":
            if self.conditional_operator not in ["=", "!="]:
                raise exceptions.UserError("Conditional Operator must be equal to '=' or '!=' for Selection Test Type.")

        conditional_map = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "=": lambda x, y: x == y,
            "!=": lambda x, y: x != y,
        }

        operation = conditional_map.get(self.conditional_operator)
        return operation(test_value, self.condition_value)
