import logging
from collections import Counter
from typing import Any, ClassVar, Self, overload

from lxml import etree
from odoo import api, fields, models
from psycopg2.errors import UniqueViolation

from .external_reference import (
    ExternalIdBinding,
    ExternalKeyLike,
    ExternalModelReference,
    ExternalOptionalKeyLike,
    ExternalRecordReference,
    ExternalResourceReference,
)

_logger = logging.getLogger(__name__)


class ExternalIdMixin(models.AbstractModel):
    _name = "external.id.mixin"
    _description = "External ID Mixin"
    _external_id_binding: ClassVar[ExternalIdBinding | None] = None
    _external_id_bindings: ClassVar[tuple[ExternalIdBinding, ...]] = ()
    _external_ids_auto_ui: ClassVar[bool] = True

    external_ids = fields.One2many(
        "external.id",
        "res_id",
        string="External IDs",
        domain=lambda self: [("res_model", "=", self._name)],
    )
    external_ids_count = fields.Integer(string="External ID Count", compute="_compute_external_ids_count")

    @property
    def external(self) -> ExternalRecordReference | ExternalModelReference:
        if len(self) == 1:
            return ExternalRecordReference(self)
        return ExternalModelReference(self)

    @property
    def external_lookup(self) -> ExternalModelReference:
        return ExternalModelReference(self)

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def external_id(self) -> str | None:
        self.ensure_one()
        return self.get_bound_external_id()

    @external_id.setter
    def external_id(self, external_id_value: str) -> None:
        self.ensure_one()
        self.set_bound_external_id(external_id_value)

    @property
    def external_id_record(self) -> "odoo.model.external_id":
        self.ensure_one()
        return self.get_bound_external_id_record()

    @property
    def external_reference(self) -> ExternalResourceReference:
        self.ensure_one()
        return self.get_bound_external_reference()

    @classmethod
    def get_bound_external_binding(cls, binding_name: str | None = None) -> ExternalIdBinding:
        return cls._get_declared_external_id_binding(binding_name)

    @classmethod
    def get_bound_external_resource_name(cls, binding_name: str | None = None) -> str:
        declared_binding = cls.get_bound_external_binding(binding_name)
        return cls._normalize_external_key(declared_binding.resource_name, default="default") or "default"

    @classmethod
    def _get_declared_external_id_bindings(cls) -> tuple[ExternalIdBinding, ...]:
        declared_bindings = getattr(cls, "_external_id_bindings", ()) or ()
        if isinstance(declared_bindings, ExternalIdBinding):
            return (declared_bindings,)
        if declared_bindings:
            return tuple(declared_bindings)

        declared_binding = getattr(cls, "_external_id_binding", None)
        if declared_binding:
            return (declared_binding,)
        return ()

    @classmethod
    def _get_declared_external_id_binding(cls, binding_name: str | None = None) -> ExternalIdBinding:
        declared_bindings = cls._get_declared_external_id_bindings()
        if not declared_bindings:
            raise ValueError(f"Model '{cls._name}' does not declare any external ID bindings")

        if binding_name is None:
            if len(declared_bindings) == 1:
                return declared_bindings[0]
            default_bindings = [binding for binding in declared_bindings if binding.is_default]
            if len(default_bindings) == 1:
                return default_bindings[0]
            raise ValueError(f"Model '{cls._name}' declares multiple external ID bindings; pass binding_name explicitly")

        normalized_binding_name = binding_name.strip()
        for declared_binding in declared_bindings:
            if declared_binding.normalized_binding_name() == normalized_binding_name:
                return declared_binding
        raise ValueError(f"External ID binding '{binding_name}' is not declared on model '{cls._name}'")

    @staticmethod
    @overload
    def _resolve_external_binding(
        system_code: ExternalIdBinding,
        resource: None = None,
    ) -> tuple[ExternalKeyLike, ExternalOptionalKeyLike]: ...

    @staticmethod
    @overload
    def _resolve_external_binding(
        system_code: ExternalKeyLike,
        resource: ExternalOptionalKeyLike = None,
    ) -> tuple[ExternalKeyLike, ExternalOptionalKeyLike]: ...

    @staticmethod
    def _resolve_external_binding(
        system_code: ExternalIdBinding | ExternalKeyLike,
        resource: ExternalOptionalKeyLike = None,
    ) -> tuple[ExternalKeyLike, ExternalOptionalKeyLike]:
        if isinstance(system_code, ExternalIdBinding):
            if resource is not None:
                raise ValueError("Do not pass a separate resource when using an ExternalIdBinding")
            return system_code.system_code, system_code.resource_name
        return system_code, resource

    @staticmethod
    def _normalize_external_key(key_value: ExternalOptionalKeyLike, default: str | None = None) -> str | None:
        if key_value is None:
            return default
        normalized_value = str(key_value).strip()
        if normalized_value:
            return normalized_value
        return default

    @staticmethod
    def _write_if_changed(record: models.Model, values: dict[str, Any]) -> bool:
        changed_values: dict[str, Any] = {}
        for field_name, incoming_value in values.items():
            if field_name not in record._fields:
                raise ValueError(f"Invalid field '{field_name}' on model '{record._name}'")
            field = record._fields[field_name]
            if field.type in {"many2many", "one2many"}:
                changed_values[field_name] = incoming_value
                continue
            current_value = record[field_name]
            if field.type == "many2one" and isinstance(current_value, models.BaseModel):
                current_value = current_value.id
            normalized_incoming_value = incoming_value
            if field.type == "many2one":
                normalized_incoming_value = getattr(incoming_value, "id", incoming_value)
            if current_value != normalized_incoming_value:
                changed_values[field_name] = incoming_value
        if not changed_values:
            return False
        record.write(changed_values)
        return True

    def _compute_external_ids_count(self) -> None:
        count_by_res_id: Counter[int] = Counter()
        if self.ids:
            external_id_records = self.env["external.id"].with_context(active_test=False).search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", self.ids),
                ]
            )
            count_by_res_id.update(int(res_id) for res_id in external_id_records.mapped("res_id") if res_id)
        for record in self:
            record.external_ids_count = count_by_res_id.get(record.id, 0)

    def _get_external_system(self, system_code: ExternalKeyLike) -> "odoo.model.external_system":
        normalized_system_code = self._normalize_external_key(system_code)
        if not normalized_system_code:
            return self.env["external.system"].browse()
        return self.env["external.system"].search([("code", "=", normalized_system_code)], limit=1)

    @api.model
    def get_view(
        self,
        view_id: int | None = None,
        view_type: str = "form",
        **options: object,
    ) -> dict[str, Any]:
        view_definition = dict(super().get_view(view_id=view_id, view_type=view_type, **options))
        return self._inject_external_ids_form_ui(view_definition, view_type)

    @classmethod
    def _inject_external_ids_form_ui(
        cls,
        view_definition: dict[str, Any],
        view_type: str,
    ) -> dict[str, Any]:
        if view_type != "form" or not cls._external_ids_auto_ui:
            return view_definition
        if "external_ids" not in getattr(cls, "_fields", {}):
            return view_definition

        architecture_source = view_definition.get("arch") or view_definition.get("arch_base")
        if not architecture_source:
            return view_definition

        architecture = etree.fromstring(architecture_source.encode())
        cls._inject_external_ids_button(architecture)
        cls._inject_external_ids_page(architecture)
        view_definition["arch"] = etree.tostring(architecture, encoding="unicode")
        return view_definition

    @classmethod
    def _inject_external_ids_button(cls, architecture: etree._Element) -> None:
        if architecture.xpath(".//button[@name='action_view_external_ids']"):
            return

        button_boxes = architecture.xpath(".//div[@name='button_box']")
        if not button_boxes:
            return

        button_boxes[0].append(
            etree.fromstring(
                """
                <button name="action_view_external_ids" type="object" class="oe_stat_button" icon="fa-link">
                    <field name="external_ids_count" widget="statinfo" string="External IDs"/>
                </button>
                """.strip()
            )
        )

    @classmethod
    def _inject_external_ids_page(cls, architecture: etree._Element) -> None:
        if architecture.xpath(".//page[@name='external_ids']"):
            return

        notebooks = architecture.xpath(".//sheet/notebook")
        if notebooks:
            notebook = notebooks[0]
        else:
            sheets = architecture.xpath(".//sheet")
            if not sheets:
                return
            notebook = etree.Element("notebook")
            sheets[0].append(notebook)

        notebook.append(etree.fromstring(cls._build_external_ids_page_arch().encode()))

    @classmethod
    def _build_external_ids_page_arch(cls) -> str:
        return f"""
        <page string="External IDs" name="external_ids">
            <field name="external_ids"
                   domain="[('res_model', '=', '{cls._name}')]"
                   context="{{'default_res_model': '{cls._name}', 'default_res_id': id}}">
                <list editable="bottom">
                    <field name="system_id"/>
                    <field name="resource"/>
                    <field name="external_id"/>
                    <field name="last_sync"/>
                    <field name="active" widget="boolean_toggle"/>
                </list>
                <form string="External ID">
                    <group>
                        <field name="system_id" options="{{'no_create_edit': True}}"/>
                        <field name="resource"/>
                        <field name="external_id"/>
                        <field name="reference" readonly="1"/>
                        <field name="last_sync" readonly="1"/>
                        <field name="notes"/>
                    </group>
                </form>
            </field>
        </page>
        """.strip()

    def get_bound_external_reference(self, binding_name: str | None = None) -> ExternalResourceReference:
        self.ensure_one()
        declared_binding = self.get_bound_external_binding(binding_name)
        return self.external.binding(declared_binding)

    def get_bound_external_id_record(
        self,
        binding_name: str | None = None,
        *,
        active_only: bool = True,
    ) -> "odoo.model.external_id":
        declared_binding = self.get_bound_external_binding(binding_name)
        return self.get_external_id_record(declared_binding, active_only=active_only)

    def get_bound_external_id(self, binding_name: str | None = None) -> str | None:
        self.ensure_one()
        external_id_record = self.get_bound_external_id_record(binding_name)
        return external_id_record.external_id if external_id_record else None

    def set_bound_external_id(self, external_id_value: str, binding_name: str | None = None) -> bool:
        declared_binding = self.get_bound_external_binding(binding_name)
        return self.set_external_id(declared_binding, external_id_value)

    def map_by_bound_external_id(
        self,
        binding_name: str | None = None,
        *,
        active_only: bool = True,
    ) -> dict[str, Self]:
        if not self.ids:
            return {}

        declared_binding = self.get_bound_external_binding(binding_name)
        system = self._get_external_system(declared_binding.system_code)
        if not system:
            return {}

        external_id_model = self.env["external.id"]
        if not active_only:
            external_id_model = external_id_model.with_context(active_test=False)

        domain = [
            ("res_model", "=", self._name),
            ("res_id", "in", self.ids),
            ("system_id", "=", system.id),
            ("resource", "=", self.get_bound_external_resource_name(binding_name)),
        ]
        if active_only:
            domain.append(("active", "=", True))

        external_id_records = external_id_model.search(domain)
        return {
            str(external_id_record.external_id): self.browse(external_id_record.res_id)
            for external_id_record in external_id_records
            if external_id_record.external_id and external_id_record.res_id in self.ids
        }

    @api.model
    def domain_by_external_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
        *,
        active_only: bool = True,
    ) -> fields.Domain:
        return self.domain_by_external_ids(
            system_code,
            [external_id_value],
            resource,
            active_only=active_only,
        )

    @api.model
    def domain_by_external_ids(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_values: list[str],
        resource: ExternalOptionalKeyLike = None,
        *,
        active_only: bool = True,
    ) -> fields.Domain:
        system_code, resource = self._resolve_external_binding(system_code, resource)
        normalized_external_ids = [
            str(external_id_value).strip()
            for external_id_value in external_id_values
            if str(external_id_value).strip()
        ]
        system = self._get_external_system(system_code)
        if not system or not normalized_external_ids:
            return fields.Domain([("id", "=", False)])

        external_id_domain = fields.Domain([
            ("res_model", "=", self._name),
            ("system_id", "=", system.id),
            ("resource", "=", self._normalize_external_key(resource, default="default")),
            ("external_id", "in", normalized_external_ids),
        ])
        if active_only:
            external_id_domain &= fields.Domain([("active", "=", True)])
        external_id_records = self.env["external.id"].with_context(active_test=False).search(external_id_domain)
        if not external_id_records:
            return fields.Domain([("id", "=", False)])
        return fields.Domain([("id", "in", external_id_records.mapped("res_id"))])

    @api.model
    def map_by_external_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_values: list[str],
        resource: ExternalOptionalKeyLike = None,
        *,
        active_only: bool = True,
    ) -> dict[str, Self]:
        system_code, resource = self._resolve_external_binding(system_code, resource)
        system = self._get_external_system(system_code)
        normalized_external_ids = [
            str(external_id_value).strip()
            for external_id_value in external_id_values
            if str(external_id_value).strip()
        ]
        if not system or not normalized_external_ids:
            return {}

        external_id_model = self.env["external.id"].with_context(active_test=False)
        domain = fields.Domain([
            ("res_model", "=", self._name),
            ("system_id", "=", system.id),
            ("resource", "=", self._normalize_external_key(resource, default="default")),
            ("external_id", "in", normalized_external_ids),
        ])
        if active_only:
            domain &= fields.Domain([("active", "=", True)])
        external_id_records = external_id_model.search(domain)
        return {
            str(external_id_record.external_id): self.browse(external_id_record.res_id)
            for external_id_record in external_id_records
            if external_id_record.external_id
        }

    @api.model
    def search_by_bound_external_id(self, external_id_value: str, binding_name: str | None = None) -> Self:
        declared_binding = self.get_bound_external_binding(binding_name)
        return self._search_by_external_id_resolved(
            system_code=declared_binding.system_code,
            external_id_value=external_id_value,
            resource=declared_binding.resource_name,
        )

    @api.model
    def get_or_create_by_bound_external_id(
        self,
        external_id_value: str,
        values: dict[str, Any],
        binding_name: str | None = None,
    ) -> Self:
        declared_binding = self.get_bound_external_binding(binding_name)
        return self.get_or_create_by_external_id(declared_binding, external_id_value, values)

    def get_external_id_record(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        resource: ExternalOptionalKeyLike = None,
        *,
        active_only: bool = True,
    ) -> "odoo.model.external_id":
        self.ensure_one()
        system_code, resource = self._resolve_external_binding(system_code, resource)
        external_id_model = self.env["external.id"]
        system = self._get_external_system(system_code)
        if not system:
            return external_id_model.browse()
        resource_key = self._normalize_external_key(resource, default="default")
        external_id_model = external_id_model.with_context(active_test=False)
        domain = [
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("system_id", "=", system.id),
            ("resource", "=", resource_key),
        ]
        if active_only:
            domain = [*domain, ("active", "=", True)]
        return external_id_model.search(domain, limit=1)

    def get_external_system_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        resource: ExternalOptionalKeyLike = None,
    ) -> str | None:
        self.ensure_one()
        external_id_record = self.get_external_id_record(system_code, resource)
        return external_id_record.external_id if external_id_record else None

    @overload
    def set_external_id(
        self,
        system_code: ExternalIdBinding,
        external_id_value: str,
        resource: None = None,
    ) -> bool: ...

    @overload
    def set_external_id(
        self,
        system_code: ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
    ) -> bool: ...

    def set_external_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
    ) -> bool:
        self.ensure_one()
        external_id_model = self.env["external.id"]
        external_id_model_all = external_id_model.with_context(active_test=False)
        system_code, resource = self._resolve_external_binding(system_code, resource)
        normalized_system_code = self._normalize_external_key(system_code)
        system = self._get_external_system(system_code)
        if not system:
            raise ValueError(f"External system with code '{normalized_system_code}' not found")

        sanitized = (external_id_value or "").strip()
        resource_key = self._normalize_external_key(resource, default="default")

        record_domain = [
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("system_id", "=", system.id),
            ("resource", "=", resource_key),
        ]
        existing = external_id_model_all.search(record_domain, limit=1)

        if not sanitized:
            if existing:
                existing.write({"active": False})
            return True

        conflicting_domain = [
            ("system_id", "=", system.id),
            ("resource", "=", resource_key),
            ("external_id", "=", sanitized),
        ]
        conflicting = external_id_model_all.search(conflicting_domain, limit=1)
        if conflicting and conflicting.res_model == self._name:
            if existing and existing.id != conflicting.id:
                existing.unlink()
            if conflicting.res_id != self.id or not conflicting.active:
                conflicting.write(
                    {
                        "res_model": self._name,
                        "res_id": self.id,
                        "active": True,
                    }
                )
            return True

        if conflicting and conflicting.res_model != self._name:
            _logger.warning(
                "Skipping external ID %s for %s(%s): already used by %s(%s).",
                sanitized,
                self._name,
                self.id,
                conflicting.res_model,
                conflicting.res_id,
            )
            return False

        if existing:
            existing.write({"external_id": sanitized, "active": True})
            return True

        try:
            with self.env.cr.savepoint():
                external_id_model.create(
                    {
                        "res_model": self._name,
                        "res_id": self.id,
                        "system_id": system.id,
                        "resource": resource_key,
                        "external_id": sanitized,
                        "active": True,
                    }
                )
                return True
        except UniqueViolation:
            existing_after_conflict = external_id_model_all.search(record_domain, limit=1)
            if existing_after_conflict:
                update_values = {}
                if existing_after_conflict.external_id != sanitized:
                    update_values["external_id"] = sanitized
                if not existing_after_conflict.active:
                    update_values["active"] = True
                if update_values:
                    existing_after_conflict.write(update_values)
                return True

            conflicting_after_conflict = external_id_model_all.search(conflicting_domain, limit=1)
            if not conflicting_after_conflict:
                raise
            if conflicting_after_conflict.res_model == self._name:
                if conflicting_after_conflict.res_id != self.id or not conflicting_after_conflict.active:
                    conflicting_after_conflict.write(
                        {
                            "res_model": self._name,
                            "res_id": self.id,
                            "active": True,
                        }
                    )
                return True

            _logger.warning(
                "Skipping external ID %s for %s(%s): already used by %s(%s).",
                sanitized,
                self._name,
                self.id,
                conflicting_after_conflict.res_model,
                conflicting_after_conflict.res_id,
            )
            return False

    @api.model
    @overload
    def search_by_external_id(
        self,
        system_code: ExternalIdBinding,
        external_id_value: str,
        resource: None = None,
    ) -> Self: ...

    @api.model
    @overload
    def search_by_external_id(
        self,
        system_code: ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
    ) -> Self: ...

    @api.model
    def search_by_external_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
    ) -> Self:
        system_code, resource = self._resolve_external_binding(system_code, resource)
        return self._search_by_external_id_resolved(system_code, external_id_value, resource)

    @api.model
    def _search_by_external_id_resolved(
        self,
        system_code: ExternalKeyLike,
        external_id_value: str,
        resource: ExternalOptionalKeyLike = None,
    ) -> Self:
        ExternalId = self.env["external.id"]
        system = self._get_external_system(system_code)
        if not system:
            return self.browse()
        resource_key = self._normalize_external_key(resource, default="default")

        dom = [
            ("res_model", "=", self._name),
            ("system_id", "=", system.id),
            ("external_id", "=", external_id_value),
            ("resource", "=", resource_key),
        ]
        external_id_record = ExternalId.search(
            [*dom],
            limit=1,
        )

        if external_id_record:
            return self.browse(external_id_record.res_id)
        return self.browse()

    def copy(self, default: dict[str, Any] | None = None) -> Self:
        self.ensure_one()
        copy_defaults = dict(default or {})
        copy_defaults.setdefault("external_ids", [(5, 0, 0)])
        return super().copy(copy_defaults)

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

    @api.model
    def get_or_create_by_external_id(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        external_id_value: str,
        values: dict[str, Any],
        resource: ExternalOptionalKeyLike = None,
    ) -> Self:
        sanitized_external_id = (external_id_value or "").strip()
        system_code, resource = self._resolve_external_binding(system_code, resource)
        record = self._search_by_external_id_resolved(
            system_code=system_code,
            external_id_value=sanitized_external_id,
            resource=resource,
        )
        if record and record.exists():
            self._write_if_changed(record, values)
            return record

        ExternalId = self.env["external.id"].with_context(active_test=False)
        normalized_system_code = self._normalize_external_key(system_code)
        system = self._get_external_system(system_code)
        if not system:
            raise ValueError(f"External system with code '{normalized_system_code}' not found")

        resource_key = self._normalize_external_key(resource, default="default")
        external_id_record = ExternalId.search(
            [
                ("system_id", "=", system.id),
                ("resource", "=", resource_key),
                ("external_id", "=", sanitized_external_id),
            ],
            limit=1,
        )
        if external_id_record:
            if external_id_record.res_model and external_id_record.res_model != self._name:
                raise ValueError(f"External ID '{sanitized_external_id}' already belongs to {external_id_record.res_model}")
            existing_record = self.browse(external_id_record.res_id).exists()
            if existing_record:
                if not external_id_record.active:
                    raise ValueError(
                        f"External ID '{sanitized_external_id}' is archived for {self._name}; reactivate or remove the mapping first"
                    )
                self._write_if_changed(existing_record, values)
                return existing_record
            record = self.create(values)
            external_id_record.write(
                {
                    "res_model": self._name,
                    "res_id": record.id,
                    "active": True,
                }
            )
            return record

        record = self.create(values)
        record.set_external_id(system_code, sanitized_external_id, resource)
        return record

    def get_external_url(
        self,
        system_code: ExternalIdBinding | ExternalKeyLike,
        kind: ExternalKeyLike = "store",
        resource: ExternalOptionalKeyLike = None,
    ) -> str | None:
        self.ensure_one()
        system_code, resource = self._resolve_external_binding(system_code, resource)
        normalized_kind = self._normalize_external_key(kind, default="store")
        if not normalized_kind:
            return None

        system = self._get_external_system(system_code)
        if not system:
            return None

        normalized_resource = self._normalize_external_key(resource)
        if normalized_resource:
            external_id_record = self.get_external_id_record(system_code, normalized_resource)
            if not external_id_record:
                return None

            candidate_codes = [normalized_kind]
            if normalized_kind in {"admin", "store", "profile"}:
                resource_specific_code = f"{normalized_resource}_{normalized_kind}"
                if resource_specific_code not in candidate_codes:
                    candidate_codes.append(resource_specific_code)

            for candidate_code in candidate_codes:
                url = external_id_record.get_url(candidate_code)
                if url:
                    return url
            return None

        template_model = self.env["external.system.url"].with_context(active_test=False)
        template_domain = [
            ("system_id", "=", system.id),
            ("active", "=", True),
            "|",
            ("res_model_id", "=", False),
            ("res_model_id.model", "=", self._name),
        ]
        templates = template_model.search(template_domain, order="res_model_id desc, sequence, id")
        if not templates:
            return None

        selected_template = None
        for template_record in templates:
            if template_record.code == normalized_kind:
                selected_template = template_record
                break

        if not selected_template and normalized_kind in {"admin", "store", "profile"}:
            suffix = f"_{normalized_kind}"
            for template_record in templates:
                if template_record.code.endswith(suffix):
                    selected_template = template_record
                    break

        if not selected_template:
            return None

        inferred_resource = self._normalize_external_key(selected_template.resource, default="default")
        external_id_record = self.get_external_id_record(system_code, inferred_resource)
        if not external_id_record:
            return None
        return external_id_record.get_url(selected_template.code)

    def action_open_external_url(self) -> "odoo.values.ir_actions_act_url | odoo.values.ir_actions_client":
        self.ensure_one()
        system_code = (self.env.context or {}).get("external_system_code")
        kind = (self.env.context or {}).get("external_url_kind", "store")
        resource = (self.env.context or {}).get("external_resource")
        url = self.get_external_url(system_code, kind, resource)
        if not url:
            notification_action = {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "External Link",
                    "message": "No configured URL or missing external ID.",
                    "type": "warning",
                },
            }
            return notification_action
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}
