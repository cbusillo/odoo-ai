from odoo import fields, models


class ProductColorTag(models.Model):
    _name = "product.color.tag"
    _description = "Product Color Tag"

    name = fields.Char(required=True)


class ProductColor(models.Model):
    _name = "product.color"
    _description = "Product Color"
    _sql_constraints = [("name_uniq", "unique (name)", "Product Color name already exists !")]

    name = fields.Char(required=True)
    color_code = fields.Char(help="The HEX color code, e.g., #FFFFFF for white.")
    applicable_tags = fields.Many2many("product.color.tag", string="Applicable For")

    def __str__(self) -> str:
        return self.name if self.name else ""
