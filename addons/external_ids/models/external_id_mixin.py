from typing import Self

from odoo import api, fields, models


class ExternalIdMixin(models.AbstractModel):
    _name = "external.id.mixin"
    _description = "External ID Mixin"

    external_ids = fields.One2many("external.id", "res_id", string="External IDs")

    def get_external_system_id(self, system_code: str, resource: str | None = None) -> str | None:
        self.ensure_one()
        ExternalId = self.env["external.id"]
        System = self.env["external.system"]
        system = System.search([("code", "=", system_code)], limit=1)
        if not system:
            return None
        dom = [
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("system_id", "=", system.id),
            ("active", "=", True),
        ]
        if resource:
            dom.append(("resource", "=", resource))
        else:
            dom.append(("resource", "=", "default"))
        rec = ExternalId.search(
            [*dom],
            limit=1,
        )
        return rec.external_id if rec else None

    def set_external_id(self, system_code: str, external_id_value: str, resource: str | None = None) -> bool:
        self.ensure_one()
        ExternalId = self.env["external.id"]
        System = self.env["external.system"]

        system = System.search([("code", "=", system_code)], limit=1)
        if not system:
            raise ValueError(f"External system with code '{system_code}' not found")

        sanitized = (external_id_value or "").strip()

        dom = [
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("system_id", "=", system.id),
        ]
        if resource:
            dom.append(("resource", "=", resource))
        else:
            dom.append(("resource", "=", "default"))
        existing = ExternalId.search(
            [*dom],
            limit=1,
        )

        if existing:
            existing.write({"external_id": sanitized, "active": True})
        else:
            ExternalId.create(
                {
                    "res_model": self._name,
                    "res_id": self.id,
                    "system_id": system.id,
                    "resource": resource or "default",
                    "external_id": sanitized,
                    "active": True,
                }
            )

        return True

    @api.model
    def search_by_external_id(self, system_code: str, external_id_value: str, resource: str | None = None) -> Self:
        ExternalId = self.env["external.id"]
        System = self.env["external.system"]

        system = System.search([("code", "=", system_code)], limit=1)
        if not system:
            return self.browse()

        dom = [
            ("res_model", "=", self._name),
            ("system_id", "=", system.id),
            ("external_id", "=", external_id_value),
        ]
        if resource:
            dom.append(("resource", "=", resource))
        else:
            dom.append(("resource", "=", "default"))
        external_id_record = ExternalId.search(
            [*dom],
            limit=1,
        )

        if external_id_record:
            return self.browse(external_id_record.res_id)
        return self.browse()

    def action_view_external_ids(self) -> "odoo.values.ir_actions_act_window":
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"External IDs for {self.display_name}",
            "res_model": "external.id",
            "view_mode": "list,form",
            "domain": [("res_model", "=", self._name), ("res_id", "=", self.id)],
            "context": {
                "default_res_model": self._name,
                "default_res_id": self.id,
                "default_reference": f"{self._name},{self.id}",
            },
        }

    @staticmethod
    def _extract_numeric_id(external_id_value: str) -> str:
        # Convert GraphQL-style GIDs like gid://shopify/Product/123456 to 123456
        import re

        m = re.search(r"/(\d+)$", external_id_value or "")
        return m.group(1) if m else (external_id_value or "")

    def get_external_url(self, system_code: str, kind: str = "store", resource: str | None = None) -> str | None:
        self.ensure_one()
        System = self.env["external.system"]
        SystemUrl = self.env["external.system.url"]

        system = System.search([("code", "=", system_code)], limit=1)
        if not system:
            return None
        # Prefer dynamic templates; fallback to legacy fields
        template = None
        url_dom = [
            ("system_id", "=", system.id),
            ("code", "=", kind),
            ("active", "=", True),
            "|",
            ("res_model_id", "=", False),
            ("res_model_id.model", "=", self._name),
        ]
        # If the template defines a resource, prefer that; otherwise we will use given/default resource.
        urls = SystemUrl.search(
            [*url_dom],
            order="res_model_id desc, sequence, id",
            limit=1,
        )
        if urls:
            template = urls.template
        elif kind in {"store", "admin"}:  # legacy compatibility
            field_name = "store_url_template" if kind == "store" else "admin_url_template"
            template = getattr(system, field_name)
        if not template:
            return None

        # Determine which resource to use for ID lookup
        res_key = resource or getattr(urls, "resource", False) or "default"
        ext_id = self.get_external_system_id(system_code, res_key)
        if not ext_id:
            return None

        tokens = {
            "id": self._extract_numeric_id(ext_id),
            "gid": ext_id,
            "model": self._name,
            "name": self.display_name,
            "code": system.code,
            "base": system.url or "",
        }
        try:
            return template.format(**tokens)
        except Exception:
            return None

    def action_open_external_url(self) -> "odoo.values.ir_actions_act_url | odoo.values.ir_actions_client":
        self.ensure_one()
        system_code = (self.env.context or {}).get("external_system_code")
        kind = (self.env.context or {}).get("external_url_kind", "store")
        resource = (self.env.context or {}).get("external_resource")
        url = self.get_external_url(system_code, kind, resource)
        if not url:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "External Link",
                    "message": "No configured URL or missing external ID.",
                    "type": "warning",
                },
            }
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}
