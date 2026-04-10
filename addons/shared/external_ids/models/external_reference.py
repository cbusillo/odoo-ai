from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from odoo import fields


class ExternalSystemCode(StrEnum):
    """Base enum type for addon-owned external system codes."""


class ExternalResourceName(StrEnum):
    """Base enum type for addon-owned external resource names."""


type ExternalKeyLike = StrEnum | str
type ExternalOptionalKeyLike = StrEnum | str | None
type ExternalSystemLike = ExternalSystemCode | str
type ExternalResourceLike = ExternalResourceName | str | None
type ExternalUrlCode = Literal["admin", "profile", "store"] | str


@dataclass(frozen=True, slots=True)
class ExternalIdBinding:
    system_code: ExternalSystemLike
    resource_name: ExternalResourceLike = None
    binding_name: str | None = None
    is_default: bool = False

    def normalized_binding_name(self) -> str:
        if self.binding_name:
            return str(self.binding_name).strip()
        if self.resource_name:
            return str(self.resource_name).strip()
        return str(self.system_code).strip()


class ExternalUrlField:
    def __init__(self, url_code: ExternalUrlCode) -> None:
        self._url_code = str(url_code).strip()
        self._attribute_name = ""

    def __set_name__(self, owner: type[object], name: str) -> None:
        self._attribute_name = name

    def __get__(self, instance: "ExternalResourceReference | None", owner: type[object]) -> "str | ExternalUrlField | None":
        if instance is None:
            return self
        return instance.url(self._url_code)

    def __set__(self, instance: object, value: object) -> None:
        raise AttributeError(f"'{self._attribute_name}' is read-only")


def external_url_field(url_code: ExternalUrlCode) -> ExternalUrlField:
    return ExternalUrlField(url_code)


class ExternalResourceReference:
    _external_id_field_names_cache: frozenset[str] | None = None
    _record: "odoo.model.external_id_mixin"
    _system_code: ExternalSystemLike
    _resource_name: ExternalResourceName | str

    def __init__(
        self,
        record: "odoo.model.external_id_mixin",
        system_code: ExternalSystemLike,
        resource_name: ExternalResourceName | str,
    ) -> None:
        object.__setattr__(self, "_record", record)
        object.__setattr__(self, "_system_code", system_code)
        object.__setattr__(self, "_resource_name", resource_name)

    def get_record(self, *, active_only: bool = True) -> "odoo.model.external_id":
        return self._record.get_external_id_record(self._system_code, self._resource_name, active_only=active_only)

    @property
    def record(self) -> "odoo.model.external_id":
        return self.get_record()

    @property
    def record_any(self) -> "odoo.model.external_id":
        return self.get_record(active_only=False)

    def get_id(self, *, active_only: bool = True) -> str | None:
        external_id_record = self.get_record(active_only=active_only)
        return external_id_record.external_id if external_id_record else None

    @property
    def id(self) -> str | None:
        return self.get_id()

    @property
    def id_any(self) -> str | None:
        return self.get_id(active_only=False)

    @id.setter
    def id(self, external_id_value: object) -> None:
        normalized_external_id = None if external_id_value is None else str(external_id_value)
        self._record.set_external_id(self._system_code, normalized_external_id, self._resource_name)

    def url(self, code: ExternalUrlCode) -> str | None:
        return self._record.get_external_url(self._system_code, code, self._resource_name)

    def _field_names(self) -> set[str]:
        field_names = type(self)._external_id_field_names_cache
        if field_names is None:
            field_names = frozenset(self._record.env["external.id"]._fields)
            type(self)._external_id_field_names_cache = field_names
        return set(field_names)

    def __getattr__(self, field_name: str) -> object:
        if field_name.startswith("_"):
            raise AttributeError(field_name)
        if field_name in self._field_names():
            external_id_record = self.record
            if not external_id_record:
                return False
            return getattr(external_id_record, field_name)
        raise AttributeError(field_name)

    def __setattr__(self, field_name: str, value: object) -> None:
        if field_name.startswith("_"):
            object.__setattr__(self, field_name, value)
            return
        if field_name == "id":
            type(self).id.fset(self, value)
            return
        if field_name not in self._field_names():
            raise AttributeError(field_name)

        external_id_record = self.record
        if not external_id_record:
            raise ValueError(
                f"Cannot set '{field_name}' before an external ID exists for {self._record.model_name}:{self._record.id}"
            )
        external_id_record.write({field_name: value})

    def __bool__(self) -> bool:
        return bool(self.record)


class ExternalSystemReference:
    _record: "odoo.model.external_id_mixin"
    _system_code: ExternalSystemLike
    _resource_reference_class: type[ExternalResourceReference] = ExternalResourceReference
    _resource_reference_classes: dict[str, type[ExternalResourceReference]] = {}

    def __init__(self, record: "odoo.model.external_id_mixin", system_code: ExternalSystemLike) -> None:
        self._record = record
        self._system_code = system_code

    @classmethod
    def _get_resource_reference_class(
        cls,
        resource_name: ExternalResourceName | str,
    ) -> type[ExternalResourceReference]:
        normalized_resource_name = str(resource_name).strip()
        if normalized_resource_name:
            reference_class = cls._resource_reference_classes.get(normalized_resource_name)
            if reference_class:
                return reference_class
        return cls._resource_reference_class

    def resource(self, resource_name: ExternalResourceName | str) -> ExternalResourceReference:
        resource_reference_class = type(self)._get_resource_reference_class(resource_name)
        return resource_reference_class(self._record, self._system_code, resource_name)

    def __getattr__(self, resource_name: str) -> ExternalResourceReference:
        if resource_name.startswith("_"):
            raise AttributeError(resource_name)
        return self.resource(resource_name)

    def __getitem__(self, resource_name: ExternalResourceName | str) -> ExternalResourceReference:
        return self.resource(resource_name)


_registered_system_reference_classes: dict[str, type[ExternalSystemReference]] = {}


def register_external_system_reference(
    system_code: ExternalSystemLike,
    reference_class: type[ExternalSystemReference],
) -> None:
    normalized_system_code = str(system_code).strip()
    if not normalized_system_code:
        raise ValueError("External system code must not be empty")
    _registered_system_reference_classes[normalized_system_code] = reference_class


class ExternalRecordReference:
    _record: "odoo.model.external_id_mixin"

    def __init__(self, record: "odoo.model.external_id_mixin") -> None:
        self._record = record

    def binding(self, binding: ExternalIdBinding) -> ExternalResourceReference:
        return self.system(binding.system_code).resource(binding.resource_name or "default")

    def system(self, system_code: ExternalSystemLike) -> ExternalSystemReference:
        normalized_system_code = str(system_code).strip()
        reference_class = _registered_system_reference_classes.get(normalized_system_code, ExternalSystemReference)
        return reference_class(self._record, system_code)

    def __getattr__(self, system_code: str) -> ExternalSystemReference:
        if system_code.startswith("_"):
            raise AttributeError(system_code)
        return self.system(system_code)

    def __getitem__(self, system_code: ExternalSystemLike) -> ExternalSystemReference:
        return self.system(system_code)


class ExternalModelResourceReference:
    def __init__(
        self,
        model: "odoo.model.external_id_mixin",
        system_code: ExternalSystemLike,
        resource_name: ExternalResourceName | str,
    ) -> None:
        self._model = model
        self._system_code = system_code
        self._resource_name = resource_name

    def get(self, external_id_value: str) -> "odoo.model.external_id_mixin":
        return self._model.search_by_external_id(self._system_code, external_id_value, self._resource_name)

    def domain(self, external_id_value: str, *, active_only: bool = True) -> fields.Domain:
        return self._model.domain_by_external_id(
            self._system_code,
            external_id_value,
            self._resource_name,
            active_only=active_only,
        )

    def domain_in(self, external_id_values: list[str], *, active_only: bool = True) -> fields.Domain:
        return self._model.domain_by_external_ids(
            self._system_code,
            external_id_values,
            self._resource_name,
            active_only=active_only,
        )

    def record(self, external_id_value: str, *, active_only: bool = True) -> "odoo.model.external_id":
        system = self._model._get_external_system(self._system_code)
        if not system:
            return self._model.env["external.id"].browse()

        domain = [
            ("res_model", "=", self._model._name),
            ("system_id", "=", system.id),
            ("resource", "=", self._model._normalize_external_key(self._resource_name, default="default")),
            ("external_id", "=", external_id_value),
        ]
        if active_only:
            domain.append(("active", "=", True))
        return self._model.env["external.id"].with_context(active_test=False).search(domain, limit=1)

    def get_or_create(self, external_id_value: str, values: dict[str, object]) -> "odoo.model.external_id_mixin":
        return self._model.get_or_create_by_external_id(self._system_code, external_id_value, values, self._resource_name)

    def map(self, external_id_values: list[str]) -> dict[str, "odoo.model.external_id_mixin"]:
        return self._model.map_by_external_id(self._system_code, external_id_values, self._resource_name)

    def set(self, record: "odoo.model.external_id_mixin", external_id_value: str) -> None:
        record.ensure_one()
        record.external[self._system_code][self._resource_name].id = external_id_value

    def __getitem__(self, external_id_value: str) -> "odoo.model.external_id_mixin":
        return self.get(str(external_id_value))


class ExternalModelSystemReference:
    def __init__(self, model: "odoo.model.external_id_mixin", system_code: ExternalSystemLike) -> None:
        self._model = model
        self._system_code = system_code

    def resource(self, resource_name: ExternalResourceName | str) -> ExternalModelResourceReference:
        return ExternalModelResourceReference(self._model, self._system_code, resource_name)

    def __getattr__(self, resource_name: str) -> ExternalModelResourceReference:
        if resource_name.startswith("_"):
            raise AttributeError(resource_name)
        return self.resource(resource_name)

    def __getitem__(self, resource_name: ExternalResourceName | str) -> ExternalModelResourceReference:
        return self.resource(resource_name)


class ExternalModelReference:
    def __init__(self, model: "odoo.model.external_id_mixin") -> None:
        self._model = model

    def system(self, system_code: ExternalSystemLike) -> ExternalModelSystemReference:
        return ExternalModelSystemReference(self._model, system_code)

    def __getattr__(self, system_code: str) -> ExternalModelSystemReference:
        if system_code.startswith("_"):
            raise AttributeError(system_code)
        return self.system(system_code)

    def __getitem__(self, system_code: ExternalSystemLike) -> ExternalModelSystemReference:
        return self.system(system_code)
