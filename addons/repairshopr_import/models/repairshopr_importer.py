import logging
import os
import re
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.repairshopr_sync_client import RepairshoprSyncClient, RepairshoprSyncConnectionSettings

_logger = logging.getLogger(__name__)

EXTERNAL_SYSTEM_CODE = "repairshopr"
EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS = (
    "base.model_res_partner",
    "product.model_product_template",
    "sale.model_sale_order",
    "account.model_account_move",
    "helpdesk.model_helpdesk_ticket",
)

RESOURCE_CUSTOMER = "customer"
RESOURCE_CONTACT = "contact"
RESOURCE_PRODUCT = "product"
RESOURCE_TICKET = "ticket"
RESOURCE_ESTIMATE = "estimate"
RESOURCE_INVOICE = "invoice"

DEFAULT_HELPDESK_TEAM_NAME = "RepairShopr"
DEFAULT_SERVICE_PRODUCT_CODE = "REPAIRSHOPR-SERVICE"

SERIAL_PATTERN = re.compile(
    r"\b(?:S\s*/?\s*N|SN|SERIAL(?:\s*(?:NO|NUMBER))?)\s*[:#\-]\s*(?P<serial>[A-Z0-9][A-Z0-9\- ]{4,25})\b",
    re.IGNORECASE,
)
ASSET_TAG_PATTERN = re.compile(
    r"\b(?:ASSET\s*TAG|ASSET|TAG)\s*[:#\-]\s*(?P<tag>[A-Z0-9][A-Z0-9\- ]{2,25})\b",
    re.IGNORECASE,
)
CLAIM_PATTERN = re.compile(
    r"\b(?:CLAIM|RMA)\s*(?:NO|NUMBER|#)?\s*[:#\-]\s*(?P<claim>[A-Z0-9][A-Z0-9\- ]{2,30})\b",
    re.IGNORECASE,
)
PO_PATTERN = re.compile(
    r"\b(?:PO|P/O|PURCHASE\s+ORDER)\s*(?:NO|NUMBER|#)?\s*[:#\-]\s*(?P<po>[A-Z0-9][A-Z0-9\- ]{2,30})\b",
    re.IGNORECASE,
)
IMEI_PATTERN = re.compile(
    r"\bIMEI\s*(?:NO|NUMBER|#)?\s*[:#\-]\s*(?P<imei>[0-9]{8,20})\b",
    re.IGNORECASE,
)
TICKET_PATTERN = re.compile(
    r"\bTICKET\s*#?\s*(?P<ticket>[0-9]+)\b",
    re.IGNORECASE,
)

IMPORT_CONTEXT = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
    "sale_no_log_for_new_lines": True,
    "skip_shopify_sync": True,
}


class RepairshoprImporter(models.Model):
    _name = "repairshopr.importer"
    _description = "RepairShopr Importer"

    @api.model
    def run_scheduled_import(self) -> None:
        self._run_import(update_last_sync=True)

    @api.model
    def run_full_import(self) -> None:
        self._run_import(update_last_sync=False)

    @api.model
    def _run_import(self, *, update_last_sync: bool) -> None:
        sync_started_at = fields.Datetime.now()
        use_last_sync_at = self._use_last_sync_at()
        start_datetime = self._get_last_sync_at() if update_last_sync and use_last_sync_at else None
        repairshopr_client = self._build_client()
        try:
            system = self._get_repairshopr_system()
            self._import_customers(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_products(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_tickets(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_estimates(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_invoices(repairshopr_client, start_datetime, system, sync_started_at)
        except Exception as exc:
            _logger.exception("RepairShopr import failed")
            self._record_last_run("failed", str(exc))
            raise
        finally:
            repairshopr_client.clear_cache()

        self._record_last_run("success", "")
        if update_last_sync and use_last_sync_at:
            self._set_last_sync_at(sync_started_at)

    def _build_client(self) -> RepairshoprSyncClient:
        settings = self._get_sync_settings()
        return RepairshoprSyncClient(settings)

    def _get_sync_settings(self) -> RepairshoprSyncConnectionSettings:
        host = self._get_config_value(
            "repairshopr.sync_db.host",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__HOST",
        )
        user = self._get_config_value(
            "repairshopr.sync_db.user",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__USER",
        )
        database = self._get_config_value(
            "repairshopr.sync_db.name",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__NAME",
        )
        password = self._get_config_value(
            "repairshopr.sync_db.password",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__PASSWORD",
        )
        port = self._get_config_int(
            "repairshopr.sync_db.port",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__PORT",
            default=3306,
        )
        use_ssl = self._get_config_bool(
            "repairshopr.sync_db.use_ssl",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__USE_SSL",
            default=True,
        )
        ssl_verify = self._get_config_bool(
            "repairshopr.sync_db.ssl_verify",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__SSL_VERIFY",
            default=True,
        )
        batch_size = self._get_config_int(
            "repairshopr.sync_db.batch_size",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__BATCH_SIZE",
            default=50,
        )
        if not use_ssl:
            _logger.warning("RepairShopr sync DB SSL disabled; enable for production.")
        if use_ssl and not ssl_verify:
            _logger.warning("RepairShopr sync DB SSL verification disabled; enable for production.")
        return RepairshoprSyncConnectionSettings(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
            batch_size=batch_size,
        )

    def _get_repairshopr_system(self) -> "odoo.model.external_system":
        return self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="RepairShopr",
            id_format=r"^\d+$",
            sequence=70,
            active=True,
            applicable_model_xml_ids=EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
        )

    def _get_last_sync_at(self) -> datetime | None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param("repairshopr.last_sync_at")
        if not value:
            return None
        try:
            return fields.Datetime.from_string(value)
        except (TypeError, ValueError):
            return None

    def _set_last_sync_at(self, value: datetime) -> None:
        self.env["ir.config_parameter"].sudo().set_param("repairshopr.last_sync_at", fields.Datetime.to_string(value))

    def _record_last_run(self, status: str, message: str) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("repairshopr.last_run_status", status)
        parameter_model.set_param("repairshopr.last_run_message", message)
        parameter_model.set_param("repairshopr.last_run_at", fields.Datetime.to_string(fields.Datetime.now()))

    def _commit_and_clear(self) -> None:
        self.env.cr.execute("SET LOCAL synchronous_commit TO OFF")
        self.env.cr.commit()
        self.env.clear()

    def _get_commit_interval(self) -> int:
        return self._get_config_int(
            "repairshopr.sync_db.batch_size",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__SYNC_DB__BATCH_SIZE",
            default=50,
        )

    def _maybe_commit(self, processed_count: int, commit_interval: int, *, label: str) -> bool:
        if commit_interval <= 0:
            return False
        if processed_count % commit_interval != 0:
            return False
        self._commit_and_clear()
        _logger.info("RepairShopr import: committed %s %s records", processed_count, label)
        return True

    def _get_external_id_record(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
    ) -> "odoo.model.external_id":
        return self.env["external.id"].sudo().search(
            [
                ("system_id", "=", system.id),
                ("resource", "=", resource),
                ("external_id", "=", external_id_value),
            ],
            limit=1,
        )

    def _should_process_external_row(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
        updated_at: datetime | None,
    ) -> bool:
        if updated_at is None:
            return True
        external_id_record = self._get_external_id_record(system, external_id_value, resource)
        if not external_id_record or not external_id_record.last_sync:
            return True
        return external_id_record.last_sync < updated_at

    def _mark_external_id_synced(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
        sync_timestamp: datetime,
    ) -> None:
        external_id_record = self._get_external_id_record(system, external_id_value, resource)
        if not external_id_record:
            return
        external_id_record.write({"last_sync": sync_timestamp})

    # noinspection DuplicatedCode
    # Duplicated with Fishbowl importer to keep logic local and avoid cross-addon coupling.
    def _prefetch_external_id_records(
        self,
        system_id: int,
        resource: str,
        external_ids: list[str],
        model_name: str,
    ) -> tuple[
        dict[str, int],
        dict[str, "odoo.model.external_id"],
        set[str],
        dict[str, datetime | None],
        dict[str, "odoo.model.external_id"],
    ]:
        if not external_ids:
            return {}, {}, set(), {}, {}
        external_id_model = self.env["external.id"].sudo().with_context(active_test=False)
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("external_id", "in", external_ids),
            ]
        )
        existing_map: dict[str, int] = {}
        stale_map: dict[str, "odoo.model.external_id"] = {}
        blocked: set[str] = set()
        last_sync_map: dict[str, datetime | None] = {}
        record_map: dict[str, "odoo.model.external_id"] = {}
        model = self.env[model_name].sudo().with_context(active_test=False)
        for record in records:
            external_id_value = record.external_id
            if not external_id_value:
                continue
            if record.res_model and record.res_model != model_name:
                blocked.add(external_id_value)
                continue
            record_map[external_id_value] = record
            last_sync_map[external_id_value] = record.last_sync
            if record.res_model == model_name:
                target = model.browse(record.res_id)
                if target.exists():
                    existing_map[external_id_value] = record.res_id
                    continue
            stale_map[external_id_value] = record
        return existing_map, stale_map, blocked, last_sync_map, record_map

    def _sync_identifier_index(
        self,
        res_model: str,
        res_id: int,
        identifiers: dict[str, set[str]],
        *,
        source_system: str,
    ) -> None:
        if not identifiers:
            return
        identifier_model = self.env["identifier.index"].sudo().with_context(IMPORT_CONTEXT)
        for identifier_type, identifier_values in identifiers.items():
            if not identifier_values:
                continue
            for identifier_value in identifier_values:
                normalized_value = self._normalize_identifier_value(identifier_value)
                if not normalized_value:
                    continue
                identifier_value_clean = identifier_value.strip()
                existing = identifier_model.with_context(active_test=False).search(
                    [
                        ("identifier_type", "=", identifier_type),
                        ("identifier_normalized", "=", normalized_value),
                        ("res_model", "=", res_model),
                        ("res_id", "=", res_id),
                    ],
                    limit=1,
                )
                if existing:
                    update_values: dict[str, object] = {}
                    if not existing.active:
                        update_values["active"] = True
                    if existing.identifier_value != identifier_value_clean:
                        update_values["identifier_value"] = identifier_value_clean
                    if existing.source_system != source_system:
                        update_values["source_system"] = source_system
                    if update_values:
                        existing.write(update_values)
                    continue
                identifier_model.create(
                    {
                        "identifier_type": identifier_type,
                        "identifier_value": identifier_value_clean,
                        "identifier_normalized": normalized_value,
                        "source_system": source_system,
                        "res_model": res_model,
                        "res_id": res_id,
                        "active": True,
                    }
                )

    @staticmethod
    def _normalize_identifier_value(identifier_value: str | None) -> str | None:
        if not identifier_value:
            return None
        normalized = re.sub(r"\s+", " ", identifier_value).strip().lower()
        return normalized or None

    @staticmethod
    def _empty_identifier_map() -> dict[str, set[str]]:
        return {
            "serial": set(),
            "asset_tag": set(),
            "asset_tag_secondary": set(),
            "imei": set(),
            "claim": set(),
            "call": set(),
            "po": set(),
            "ticket": set(),
            "invoice": set(),
            "delivery": set(),
            "bid": set(),
        }

    @staticmethod
    def _merge_identifier_maps(
            target: dict[str, set[str]],
        source: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        if not source:
            return target
        for identifier_type, values in source.items():
            if not values:
                continue
            target.setdefault(identifier_type, set()).update(values)
        return target

    def _extract_identifiers_from_text(self, text: str | None) -> dict[str, set[str]]:
        identifiers = self._empty_identifier_map()
        if not text:
            return identifiers
        for match in SERIAL_PATTERN.finditer(text):
            serial_value = match.group("serial").strip()
            if serial_value:
                identifiers["serial"].add(serial_value)
        for match in ASSET_TAG_PATTERN.finditer(text):
            tag_value = match.group("tag").strip()
            if tag_value:
                identifiers["asset_tag"].add(tag_value)
        for match in CLAIM_PATTERN.finditer(text):
            claim_value = match.group("claim").strip()
            if claim_value:
                identifiers["claim"].add(claim_value)
        for match in PO_PATTERN.finditer(text):
            po_value = match.group("po").strip()
            if po_value:
                identifiers["po"].add(po_value)
        for match in IMEI_PATTERN.finditer(text):
            imei_value = match.group("imei").strip()
            if imei_value:
                identifiers["imei"].add(imei_value)
        for match in TICKET_PATTERN.finditer(text):
            ticket_value = match.group("ticket").strip()
            if ticket_value:
                identifiers["ticket"].add(ticket_value)
        return identifiers

    def _collect_identifiers_from_ticket_properties(self, properties: object) -> dict[str, set[str]]:
        identifiers = self._empty_identifier_map()
        if not properties:
            return identifiers
        serial_value = getattr(properties, "s_n_num", None) or getattr(properties, "s_n", None)
        if serial_value:
            identifiers["serial"].add(str(serial_value).strip())
        tag_value = getattr(properties, "tag_num", None)
        if tag_value:
            identifiers["asset_tag"].add(str(tag_value).strip())
        secondary_tag = getattr(properties, "tag_num_2", None)
        if secondary_tag:
            identifiers["asset_tag_secondary"].add(str(secondary_tag).strip())
        claim_value = getattr(properties, "claim_num", None)
        if claim_value:
            identifiers["claim"].add(str(claim_value).strip())
        delivery_value = getattr(properties, "delivery_num", None)
        if delivery_value:
            identifiers["delivery"].add(str(delivery_value).strip())
        call_value = getattr(properties, "call_num", None)
        if call_value:
            identifiers["call"].add(str(call_value).strip())
        po_value = getattr(properties, "po_num_2", None)
        if po_value:
            identifiers["po"].add(str(po_value).strip())
        return identifiers

    def _collect_identifiers_from_line_items(self, line_items: list[dict[str, object]]) -> dict[str, set[str]]:
        identifiers = self._empty_identifier_map()
        if not line_items:
            return identifiers
        for line_item in line_items:
            text = line_item.get("name") or line_item.get("item") or ""
            if not text:
                continue
            parsed = self._extract_identifiers_from_text(str(text))
            self._merge_identifier_maps(identifiers, parsed)
        return identifiers

    def _get_config_value(self, key: str, env_key: str, *, required: bool = True) -> str:
        value = self._get_config_raw_value(key, env_key)
        if required and not value:
            raise UserError(f"Missing configuration for {key}.")
        return value

    def _get_config_bool(self, key: str, env_key: str, *, default: bool) -> bool:
        value = self._get_config_raw_value(key, env_key)
        if not value:
            return default
        return self._to_bool(value)

    def _use_last_sync_at(self) -> bool:
        return self._get_config_bool(
            "repairshopr.use_last_sync_at",
            "ENV_OVERRIDE_CONFIG_PARAM__REPAIRSHOPR__USE_LAST_SYNC_AT",
            default=True,
        )

    def _resolve_partner_for_customer_id(
        self,
        customer_id: int | None,
        fallback_name: str | None,
        system_id: int,
        partner_cache: dict[int, int],
    ) -> int | None:
        customer_id_value = customer_id or 0
        if not customer_id_value:
            return None
        if customer_id_value in partner_cache:
            return partner_cache[customer_id_value] or None
        external_id_model = self.env["external.id"].sudo().with_context(active_test=False)
        external_id_record = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", RESOURCE_CUSTOMER),
                ("external_id", "=", str(customer_id_value)),
                ("res_model", "=", "res.partner"),
            ],
            limit=1,
        )
        partner_id = external_id_record.res_id if external_id_record else None
        if not partner_id:
            partner = self._get_or_create_partner_by_customer_id(customer_id_value, fallback_name)
            partner_id = partner.id if partner else None
        partner_cache[customer_id_value] = partner_id or 0
        return partner_id

    def _resolve_billing_contract_cached(
        self,
        partner: "odoo.model.res_partner",
        billing_cache: dict[int, int | None],
    ) -> "odoo.model.school_billing_contract | None":
        if not partner:
            return None
        partner_id = partner.id
        if partner_id in billing_cache:
            contract_id = billing_cache[partner_id]
            return self.env["school.billing.contract"].browse(contract_id) if contract_id else None
        contract = self._resolve_billing_contract(partner)
        billing_cache[partner_id] = contract.id if contract else None
        return contract

    def _resolve_billing_contract(
        self,
        partner: "odoo.model.res_partner | None",
    ) -> "odoo.model.school_billing_contract | None":
        if not partner:
            return None
        contract_model = self._get_billing_contract_model()
        if not contract_model:
            return None
        commercial_partner = partner.commercial_partner_id or partner
        today = fields.Date.today()
        return contract_model.search(
            [
                ("partner_id", "=", commercial_partner.id),
                ("active", "=", True),
                "|",
                ("date_start", "=", False),
                ("date_start", "<=", today),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", today),
            ],
            order="sequence, id",
            limit=1,
        )

    def _get_billing_contract_model(self) -> "odoo.model.school_billing_contract | None":
        if "school.billing.contract" not in self.env.registry.models:
            return None
        return self.env["school.billing.contract"].sudo().with_context(IMPORT_CONTEXT)

    def _get_config_int(self, key: str, env_key: str, *, default: int) -> int:
        value = self._get_config_raw_value(key, env_key)
        if not value:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise UserError(f"Invalid integer for {key}.") from exc

    def _get_config_raw_value(self, key: str, env_key: str) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        return value

    # noinspection DuplicatedCode
    # Duplicated with Fishbowl importer to keep parsing local and avoid cross-addon coupling.
    @staticmethod
    def _to_bool(value: object) -> bool:
        if value in (True, False):
            return bool(value)
        if value is None:
            return False
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw_value = bytes(value)
            if not raw_value:
                return False
            if all(byte in (0, 1) for byte in raw_value):
                return any(byte == 1 for byte in raw_value)
            try:
                decoded = raw_value.decode().strip()
            except UnicodeDecodeError:
                return any(raw_value)
            return RepairshoprImporter._to_bool(decoded)
        if isinstance(value, (int, float)):
            return bool(value)
        value_str = str(value).strip().lower()
        return value_str in {"1", "true", "yes", "on", "y", "t"}
