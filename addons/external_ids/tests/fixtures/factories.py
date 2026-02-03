from typing import Any
from odoo.api import Environment


class ExternalSystemFactory:
    @staticmethod
    def create(env: Environment, *, reuse_existing: bool = False, **kwargs: Any) -> Any:
        values = {
            "name": f"Test System {env.cr.dbname}",
            "code": f"test_{env.cr.dbname}",
            "active": True,
            "id_format": False,
            "id_prefix": "TEST-",
        }
        values.update(kwargs)
        external_system_model = env["external.system"].with_context(active_test=False)
        if reuse_existing:
            code_value = values.get("code")
            name_value = values.get("name")
            existing = None
            if code_value:
                existing = external_system_model.search([("code", "=", code_value)], limit=1)
            if not existing and name_value:
                existing = external_system_model.search([("name", "=", name_value)], limit=1)
            if existing:
                existing.write(values)
                return existing
        return external_system_model.create(values)


class ExternalIdFactory:
    @staticmethod
    def create(env: Environment, **kwargs: Any) -> Any:
        if "system_id" not in kwargs:
            system = ExternalSystemFactory.create(env)
            kwargs["system_id"] = system.id

        defaults = {
            "external_id": f"EXT-{env.cr.dbname}",
        }
        defaults.update(kwargs)
        return env["external.id"].create(defaults)
