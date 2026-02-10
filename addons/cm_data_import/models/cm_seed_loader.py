import json
import logging
import os
from pathlib import Path

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CmSeedLoader(models.Model):
    _name = "integration.cm_seed.loader"
    _description = "CM Seed Loader"

    @api.model
    def run_seed(self) -> None:
        self._load_billing_requirements()
        self._load_billing_contexts()
        self._load_helpdesk_stages()
        self._load_helpdesk_tags()
        self._load_quality_control_checklist()
        self._load_location_options()
        self._load_location_option_aliases()
        self._load_delivery_days()
        self._load_delivery_day_aliases()
        self._load_return_methods()
        self._load_return_method_aliases()
        self._load_diagnostic_tests()

    def _load_billing_requirements(self) -> None:
        raw = self._get_seed_payload("CM_SEED_BILLING_REQUIREMENTS", "billing_requirements")
        if not raw:
            return
        model = self.env["school.billing.requirement"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "code": item["code"],
                "description": item.get("description"),
                "sequence": item.get("sequence", 10),
                "active": item.get("active", True),
                "is_required": item.get("is_required", True),
                "requirement_group": item.get("requirement_group", "both"),
                "target_model": item.get("target_model"),
                "field_name": item.get("field_name"),
            }
            existing = model.search([("code", "=", item["code"])], limit=1)
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_billing_contexts(self) -> None:
        raw = self._get_seed_payload("CM_SEED_BILLING_CONTEXTS", "billing_contexts")
        if not raw:
            return
        model = self.env["school.billing.context"].sudo()
        requirement_model = self.env["school.billing.requirement"].sudo()
        for item in raw:
            requirements = requirement_model.search([("code", "in", item.get("requirements", []))])
            values = {
                "name": item["name"],
                "code": item["code"],
                "description": item.get("description"),
                "sequence": item.get("sequence", 10),
                "active": item.get("active", True),
                "requires_estimate": item.get("requires_estimate", False),
                "requires_claim_approval": item.get("requires_claim_approval", False),
                "requires_call_authorization": item.get("requires_call_authorization", False),
                "requires_payment_on_pickup": item.get("requires_payment_on_pickup", False),
                "requirement_ids": [(6, 0, requirements.ids)],
            }
            existing = model.search([("code", "=", item["code"])], limit=1)
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_helpdesk_stages(self) -> None:
        raw = self._get_seed_payload("CM_SEED_HELPDESK_STAGES", "helpdesk_stages")
        if not raw:
            return
        model = self.env["helpdesk.stage"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "sequence": item.get("sequence", 10),
                "is_close": item.get("is_close", False),
                "fold": item.get("fold", False),
            }
            existing = model.search([("name", "=", item["name"])], limit=1)
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_helpdesk_tags(self) -> None:
        raw = self._get_seed_payload("CM_SEED_HELPDESK_TAGS", "helpdesk_tags")
        if not raw:
            return
        model = self.env["helpdesk.tag"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
            }
            existing = model.search([("name", "=", item["name"])], limit=1)
            if existing:
                continue
            model.create(values)

    def _load_quality_control_checklist(self) -> None:
        raw = self._get_seed_payload("CM_SEED_QC_CHECKLIST", "qc_checklist")
        if not raw:
            return
        model = self.env["service.quality.control.checklist.item"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "category": item.get("category", "other"),
                "description": item.get("description"),
                "sequence": item.get("sequence", 10),
                "active": item.get("active", True),
            }
            existing = model.search([("name", "=", item["name"])], limit=1)
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_return_methods(self) -> None:
        raw = self._get_seed_payload("CM_SEED_RETURN_METHODS", "return_methods")
        if not raw:
            return
        model = self.env["school.return.method"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "partner_id": item.get("partner_id"),
                "external_key": item.get("external_key"),
                "sequence": item.get("sequence", 10),
                "active": item.get("active", True),
            }
            existing = model.search(
                [
                    ("partner_id", "=", item.get("partner_id")),
                    ("name", "=", item["name"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_return_method_aliases(self) -> None:
        raw = self._get_seed_payload("CM_SEED_RETURN_METHOD_ALIASES", "return_method_aliases")
        if not raw:
            return
        alias_model = self.env["school.return.method"].sudo()
        for item in raw:
            method = alias_model.search([("name", "=", item["name"])], limit=1)
            if not method:
                continue
            external_key = str(item["external_key"])
            if not method.external_key:
                method.external_key = external_key

    def _load_diagnostic_tests(self) -> None:
        raw = self._get_seed_payload("CM_SEED_DIAGNOSTIC_TESTS", "diagnostic_tests")
        if not raw:
            return
        model = self.env["service.diagnostic.test"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "description": item.get("description"),
            }
            existing = model.search([("name", "=", item["name"])], limit=1)
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_location_options(self) -> None:
        raw = self._get_seed_payload("CM_SEED_LOCATION_OPTIONS", "location_options")
        if not raw:
            return
        model = self.env["school.location.option"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "partner_id": item.get("partner_id"),
                "location_type": item.get("location_type", "location"),
                "external_key": item.get("external_key"),
                "active": item.get("active", True),
            }
            existing = model.search(
                [
                    ("partner_id", "=", item.get("partner_id")),
                    ("location_type", "=", values["location_type"]),
                    ("name", "=", item["name"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_location_option_aliases(self) -> None:
        raw = self._get_seed_payload("CM_SEED_LOCATION_OPTION_ALIASES", "location_option_aliases")
        if not raw:
            return
        alias_model = self.env["school.location.option.alias"].sudo()
        option_model = self.env["school.location.option"].sudo()
        system = self._get_repairshopr_system()
        for item in raw:
            option = option_model.search(
                [
                    ("partner_id", "=", item.get("partner_id")),
                    ("location_type", "=", item.get("location_type", "location")),
                    ("name", "=", item["name"]),
                ],
                limit=1,
            )
            if not option:
                continue
            values = {
                "location_option_id": option.id,
                "system_id": system.id,
                "external_key": str(item["external_key"]),
                "active": item.get("active", True),
            }
            existing = alias_model.search(
                [
                    ("system_id", "=", system.id),
                    ("external_key", "=", values["external_key"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                alias_model.create(values)

    def _load_delivery_days(self) -> None:
        raw = self._get_seed_payload("CM_SEED_DELIVERY_DAYS", "delivery_days")
        if not raw:
            return
        model = self.env["school.delivery.day"].sudo()
        for item in raw:
            values = {
                "name": item["name"],
                "code": item.get("code"),
                "partner_id": item.get("partner_id"),
                "sequence": item.get("sequence", 10),
                "active": item.get("active", True),
            }
            existing = model.search(
                [
                    ("partner_id", "=", item.get("partner_id")),
                    ("name", "=", item["name"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                model.create(values)

    def _load_delivery_day_aliases(self) -> None:
        raw = self._get_seed_payload("CM_SEED_DELIVERY_DAY_ALIASES", "delivery_day_aliases")
        if not raw:
            return
        alias_model = self.env["school.delivery.day.alias"].sudo()
        day_model = self.env["school.delivery.day"].sudo()
        system = self._get_repairshopr_system()
        for item in raw:
            day = day_model.search(
                [
                    ("partner_id", "=", item.get("partner_id")),
                    ("name", "=", item["name"]),
                ],
                limit=1,
            )
            if not day:
                continue
            values = {
                "delivery_day_id": day.id,
                "system_id": system.id,
                "external_key": str(item["external_key"]),
                "active": item.get("active", True),
            }
            existing = alias_model.search(
                [
                    ("system_id", "=", system.id),
                    ("external_key", "=", values["external_key"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                alias_model.create(values)

    def _get_seed_payload(self, param_key: str, file_key: str) -> list[dict] | None:
        file_payload = self._get_seed_file_payload()
        if file_payload and file_key in file_payload:
            payload = file_payload[file_key]
            if not isinstance(payload, list):
                raise UserError(f"Seed file payload '{file_key}' must be a JSON array.")
            return payload
        return self._get_seed_json(param_key)

    def _get_seed_json(self, param_key: str) -> list[dict] | None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        raw = parameter_model.get_param(param_key) or ""
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UserError(f"Invalid JSON in {param_key}.") from exc
        if not isinstance(payload, list):
            raise UserError(f"{param_key} must be a JSON array.")
        return payload

    def _get_seed_file_payload(self) -> dict[str, list[dict]] | None:
        file_path = self._get_seed_file_path()
        if not file_path:
            return None

        path = Path(file_path)
        if not path.exists():
            raise UserError(f"Seed file not found: {file_path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UserError(f"Invalid JSON in seed file: {file_path}") from exc

        if not isinstance(payload, dict):
            raise UserError("Seed file must contain a JSON object at the top level.")

        return payload

    def _get_seed_file_path(self) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param("cm_seed.file_path") or ""
        if not value:
            value = os.environ.get("CM_SEED_FILE_PATH", "")
        if not value:
            value = os.environ.get("ENV_OVERRIDE_CONFIG_PARAM__CM_SEED__FILE_PATH", "")
        return value

    def _get_repairshopr_system(self) -> "odoo.model.external_system":
        system_model = self.env["external.system"].sudo()
        return system_model.ensure_system(code="repairshopr", name="RepairShopr")
