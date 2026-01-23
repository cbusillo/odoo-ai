from odoo import fields, models

IDENTIFIER_TYPES = [
    ("serial", "Serial Number"),
    ("asset_tag", "Asset Tag"),
    ("asset_tag_secondary", "Asset Tag (Secondary)"),
    ("imei", "IMEI"),
    ("claim", "Claim Number"),
    ("call", "Call Number"),
    ("po", "PO Number"),
    ("ticket", "Ticket Number"),
    ("invoice", "Invoice Number"),
    ("delivery", "Delivery Number"),
    ("bid", "Bid Number"),
]


class IdentifierIndex(models.Model):
    _name = "identifier.index"
    _description = "Identifier Index"
    _order = "identifier_type, identifier_value, id"

    identifier_type = fields.Selection(
        IDENTIFIER_TYPES,
        required=True,
    )
    identifier_value = fields.Char(required=True)
    identifier_normalized = fields.Char(index=True)
    source_system = fields.Char()
    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _identifier_unique = models.Constraint(
        "unique(identifier_type, identifier_normalized, res_model, res_id)",
        "Identifier already linked to this record.",
    )
