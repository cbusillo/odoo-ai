from odoo import fields, models

from .external_reference import ExternalIdBinding


class ExternalIdFixture(models.Model):
    _name = "external.id.fixture"
    _description = "External ID Fixture"
    _inherit = ["external.id.mixin"]
    _external_id_binding = ExternalIdBinding(system_code="discord")

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
