from typing import Any
from odoo.api import Environment


class ExternalSystemFactory:
    @staticmethod
    def create(env: Environment, **kwargs: Any) -> Any:
        defaults = {
            "name": f"Test System {env.cr.dbname}",
            "code": f"test_{env.cr.dbname}",
            "active": True,
            "id_format": r"^[A-Z0-9]+$",
            "id_prefix": "TEST-",
        }
        defaults.update(kwargs)
        return env["external.system"].create(defaults)


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
