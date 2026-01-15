import logging
import os

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

AUTHENTIK_PREFIX = "ENV_OVERRIDE_AUTHENTIK__"
DEFAULT_AUTHENTIK_ADMIN_GROUP = "authentik Admins"


class AuthentikSsoGroupMapping(models.Model):
    _name = "authentik.sso.group.mapping"
    _description = "Authentik group mapping"
    _order = "sequence, id"

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    authentik_group = fields.Char(string="Authentik Group")
    odoo_groups = fields.Many2many(
        "res.groups",
        "authentik_sso_group_mapping_rel",
        "mapping_id",
        "group_id",
        string="Odoo Groups",
    )
    is_fallback = fields.Boolean(string="Fallback (no Authentik group)", default=False)

    @api.constrains("is_fallback")
    def _check_single_fallback(self) -> None:
        for record in self:
            if not record.is_fallback:
                continue
            fallback_count = self.search_count([("is_fallback", "=", True)])
            if fallback_count > 1:
                raise ValidationError(self.env._("Only one fallback mapping is allowed."))

    @api.constrains("authentik_group", "is_fallback")
    def _check_authentik_group(self) -> None:
        for record in self:
            if record.is_fallback:
                if record.authentik_group:
                    raise ValidationError(self.env._("Fallback mapping must not set an Authentik group."))
                continue
            if not record.authentik_group:
                raise ValidationError(self.env._("Authentik group is required unless this is a fallback."))

    @api.model
    def _resolve_admin_group_name(self) -> str:
        raw_value = os.environ.get(f"{AUTHENTIK_PREFIX}ADMIN_GROUP")
        if raw_value is None:
            return DEFAULT_AUTHENTIK_ADMIN_GROUP
        cleaned = raw_value.strip()
        return cleaned or DEFAULT_AUTHENTIK_ADMIN_GROUP

    @api.model
    def _default_admin_groups(self) -> list[int]:
        group_model = self.env["res.groups"].sudo()
        admin_groups = group_model.search([("name", "ilike", "Admin")])
        admin_groups |= group_model.search([("name", "ilike", "Manager")])

        data_model = self.env["ir.model.data"].sudo()
        data_records = data_model.search(
            [
                ("model", "=", "res.groups"),
                "|",
                ("name", "ilike", "%manager%"),
                ("name", "ilike", "%admin%"),
            ]
        )
        if data_records:
            admin_groups |= group_model.browse(data_records.mapped("res_id"))

        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        if system_group:
            admin_groups |= system_group

        unique_ids = sorted({group.id for group in admin_groups})
        return unique_ids

    @api.model
    def ensure_default_mappings(self) -> None:
        mapping_model = self.sudo()
        fallback_mapping = mapping_model.search([("is_fallback", "=", True)], limit=1)
        if not fallback_mapping:
            base_user_group = self.env.ref("base.group_user", raise_if_not_found=False)
            mapping_model.create(
                {
                    "is_fallback": True,
                    "odoo_groups": [(6, 0, [base_user_group.id])] if base_user_group else [],
                    "sequence": 10,
                }
            )

        admin_group_name = self._resolve_admin_group_name()
        admin_mapping = mapping_model.search(
            [
                ("authentik_group", "=", admin_group_name),
                ("is_fallback", "=", False),
            ],
            limit=1,
        )
        if not admin_mapping:
            admin_mapping = mapping_model.create(
                {
                    "authentik_group": admin_group_name,
                    "sequence": 20,
                }
            )

        default_record = self.env.ref("authentik_sso.authentik_group_mapping_admins", raise_if_not_found=False)
        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        current_group_ids = set(admin_mapping.odoo_groups.ids)
        allow_seed = not current_group_ids
        if default_record and admin_mapping.id == default_record.id:
            if system_group and current_group_ids == {system_group.id}:
                allow_seed = True

        if allow_seed:
            admin_group_ids = self._default_admin_groups()
            admin_mapping.write({"odoo_groups": [(6, 0, admin_group_ids)]})
            _logger.info("Initialized Authentik admin group mapping with %d groups.", len(admin_group_ids))
