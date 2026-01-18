from __future__ import annotations

import logging
import os
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.cm_data_client import (
    CmDataAccountName,
    CmDataClient,
    CmDataConnectionSettings,
    CmDataContact,
    CmDataDeliveryLog,
)

_logger = logging.getLogger(__name__)

EXTERNAL_SYSTEM_CODE = "cm-data"
EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS = (
    "base.model_res_partner",
    "cm_transport.model_transport_order",
)

RESOURCE_ACCOUNT = "school_account"
RESOURCE_CONTACT = "school_contact"
RESOURCE_DELIVERY_LOG = "delivery_log"

IMPORT_CONTEXT: dict[str, bool] = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
}


class CmDataImporter(models.Model):
    _name = "cm.data.importer"
    _description = "CM Data Importer"

    @api.model
    def run_scheduled_import(self) -> None:
        self._run_import(update_last_sync=True)

    @api.model
    def run_full_import(self) -> None:
        self._run_import(update_last_sync=False)

    @api.model
    def _run_import(self, *, update_last_sync: bool) -> None:
        run_started_at = fields.Datetime.now()
        start_datetime = self._get_last_sync_at() if update_last_sync else None
        settings = self._get_sync_settings()
        client = CmDataClient(settings)
        try:
            self._get_cm_data_system()
            with client:
                accounts = client.fetch_account_names(None)
                partner_map = self._import_school_accounts(accounts)
                self._import_contacts(client.fetch_contacts(start_datetime), partner_map)
                self._import_delivery_logs(client.fetch_delivery_logs(start_datetime), partner_map)
        except Exception as exc:
            _logger.exception("CM data import failed")
            self._record_last_run("failed", str(exc))
            raise
        finally:
            client.clear_cache()

        self._record_last_run("success", "")
        if update_last_sync:
            self._set_last_sync_at(run_started_at)

    def _get_sync_settings(self) -> CmDataConnectionSettings:
        host = self._get_config_value(
            "cm_data.db.host",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__HOST",
            fallback_env="CM_DATA_DB_HOST",
        )
        user = self._get_config_value(
            "cm_data.db.user",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__USER",
            fallback_env="CM_DATA_DB_USER",
        )
        password = self._get_config_value(
            "cm_data.db.password",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__PASSWORD",
            fallback_env="CM_DATA_DB_PASSWORD",
        )
        database = self._get_config_value(
            "cm_data.db.name",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__NAME",
            fallback_env="CM_DATA_DB_NAME",
            required=False,
        )
        port = self._get_config_int(
            "cm_data.db.port",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__PORT",
            fallback_env="CM_DATA_DB_PORT",
            default=3306,
        )
        use_ssl = self._get_config_bool(
            "cm_data.db.use_ssl",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__USE_SSL",
            fallback_env="CM_DATA_DB_USE_SSL",
            default=False,
        )
        ssl_verify = self._get_config_bool(
            "cm_data.db.ssl_verify",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__SSL_VERIFY",
            fallback_env="CM_DATA_DB_SSL_VERIFY",
            default=True,
        )
        if not use_ssl:
            _logger.warning("CM data SSL disabled; enable for production when supported.")
        if use_ssl and not ssl_verify:
            _logger.warning("CM data SSL verification disabled; enable for production.")
        return CmDataConnectionSettings(
            host=host,
            user=user,
            password=password,
            port=port,
            database=database or None,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
        )

    def _get_cm_data_system(self) -> "odoo.model.external_system":
        return self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="CM Data",
            id_format=r"^\d+$",
            sequence=50,
            active=True,
            applicable_model_xml_ids=EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
        )

    def _import_school_accounts(
        self,
        accounts: list[CmDataAccountName],
    ) -> dict[str, "odoo.model.res_partner"]:
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        partner_map: dict[str, "odoo.model.res_partner"] = {}
        for account in accounts:
            partner = partner_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(account.record_id),
                RESOURCE_ACCOUNT,
            )
            values: "odoo.values.res_partner" = {
                "name": account.account_name,
                "company_type": "company",
                "is_company": True,
                "customer_rank": 1,
                "active": True,
                "cm_data_ticket_name": account.ticket_name,
                "cm_data_label_names": account.label_names,
                "cm_data_location_drop": account.location_drop,
                "cm_data_priority_flag": account.priority_flag,
                "cm_data_on_delivery_schedule": account.on_delivery_schedule,
                "cm_data_shipping_enable": account.shipping_enable,
            }
            if partner:
                partner.write(values)
            else:
                partner = partner_model.create(values)
                partner.set_external_id(EXTERNAL_SYSTEM_CODE, str(account.record_id), RESOURCE_ACCOUNT)
            self._assign_partner_roles(partner, {"district"})
            for key in self._build_partner_keys(account):
                partner_map[key] = partner
        return partner_map

    def _import_contacts(
        self,
        contacts: list[CmDataContact],
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> None:
        if not contacts:
            return
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        for contact in contacts:
            parent_partner = self._ensure_partner_for_account(contact.account_name, partner_map)
            if not parent_partner:
                _logger.warning(
                    "Skipping CM data contact %s; unknown account '%s'.",
                    contact.record_id,
                    contact.account_name,
                )
                continue
            contact_name = contact.sub_name or f"{contact.account_name} Contact"
            contact_partner = partner_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(contact.record_id),
                RESOURCE_CONTACT,
            )
            values: "odoo.values.res_partner" = {
                "name": contact_name,
                "company_type": "person",
                "is_company": False,
                "parent_id": parent_partner.id,
                "type": "contact",
                "active": True,
                "cm_data_contact_notes": contact.contact_notes,
                "cm_data_contact_sort_order": contact.sort_order,
            }
            if contact_partner:
                contact_partner.write(values)
            else:
                contact_partner = partner_model.create(values)
                contact_partner.set_external_id(EXTERNAL_SYSTEM_CODE, str(contact.record_id), RESOURCE_CONTACT)
            self._assign_partner_roles(contact_partner, {"school_contact"})

    def _import_delivery_logs(
        self,
        deliveries: list[CmDataDeliveryLog],
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> None:
        if not deliveries:
            return
        transport_order_model = self.env["transport.order"].sudo().with_context(IMPORT_CONTEXT)
        employee_partner = self.env.user.partner_id
        for delivery in deliveries:
            client_partner = self._ensure_partner_for_account(delivery.location_name, partner_map)
            if not client_partner:
                _logger.warning(
                    "Skipping CM data delivery log %s; unknown account '%s'.",
                    delivery.record_id,
                    delivery.location_name,
                )
                continue
            contact_partner = client_partner
            values: "odoo.values.transport_order" = {
                "name": delivery.location_name,
                "state": self._map_transport_state(delivery.status),
                "arrival_date": delivery.updated_at or delivery.created_at,
                "scheduled_date": delivery.created_at or delivery.updated_at,
                "employee": employee_partner.id,
                "client": client_partner.id,
                "contact": contact_partner.id,
                "quantity_in_counted": delivery.units,
                "cm_data_status_raw": delivery.status,
                "cm_data_location_name": delivery.location_name,
                "cm_data_location_id": delivery.location_id,
                "cm_data_units": delivery.units,
                "cm_data_notes": delivery.notes,
                "cm_data_edit_notes": delivery.edit_notes,
                "cm_data_ocr_notes": delivery.ocr_notes,
                "cm_data_discord_name": delivery.discord_name,
                "cm_data_discord_id": str(delivery.discord_id) if delivery.discord_id else None,
            }
            transport_order = transport_order_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(delivery.record_id),
                RESOURCE_DELIVERY_LOG,
            )
            if transport_order:
                self._write_if_changed(transport_order, values)
            else:
                transport_order = transport_order_model.create(values)
                transport_order.set_external_id(
                    EXTERNAL_SYSTEM_CODE,
                    str(delivery.record_id),
                    RESOURCE_DELIVERY_LOG,
                )

    def _ensure_partner_for_account(
        self,
        account_name: str,
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> "odoo.model.res_partner | None":
        key = self._normalize_partner_key(account_name)
        partner = partner_map.get(key)
        return partner

    @staticmethod
    def _build_partner_keys(account: CmDataAccountName) -> list[str]:
        keys = [account.account_name]
        if account.ticket_name:
            keys.append(account.ticket_name)
        if account.label_names:
            keys.extend(value.strip() for value in account.label_names.split(",") if value.strip())
        return [CmDataImporter._normalize_partner_key(value) for value in keys if value]

    @staticmethod
    def _normalize_partner_key(value: str) -> str:
        normalized = " ".join(value.strip().lower().split())
        return normalized

    @staticmethod
    def _map_transport_state(status: str) -> str:
        mapping = {
            "pending": "ready",
            "picked up": "transit_in",
            "delivered": "at_client",
            "buybacks": "at_depot",
            "cancelled": "draft",
            "projected return": "ready",
        }
        normalized = (status or "").strip().lower()
        return mapping.get(normalized, "draft")

    def _assign_partner_roles(self, partner: "odoo.model.res_partner", role_codes: set[str]) -> None:
        if not role_codes:
            return
        role_model = self.env["cm.partner.role"].sudo()
        roles = role_model.search([("code", "in", list(role_codes))])
        if not roles:
            return
        existing_ids = set(partner.cm_partner_role_ids.ids)
        merged_ids = list(existing_ids.union(set(roles.ids)))
        partner.write({"cm_partner_role_ids": [(6, 0, merged_ids)]})

    def _get_last_sync_at(self) -> datetime | None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param("cm_data.last_sync_at")
        if not value:
            return None
        try:
            return fields.Datetime.from_string(value)
        except (TypeError, ValueError):
            return None

    def _set_last_sync_at(self, value: datetime) -> None:
        self.env["ir.config_parameter"].sudo().set_param("cm_data.last_sync_at", fields.Datetime.to_string(value))

    def _record_last_run(self, status: str, message: str) -> None:
        parameter_model = self.env["ir.config_parameter"].sudo()
        parameter_model.set_param("cm_data.last_run_status", status)
        parameter_model.set_param("cm_data.last_run_message", message)
        parameter_model.set_param("cm_data.last_run_at", fields.Datetime.to_string(fields.Datetime.now()))

    def _get_config_value(
        self,
        key: str,
        env_key: str,
        *,
        fallback_env: str | None = None,
        required: bool = True,
    ) -> str:
        value = self._get_config_raw_value(key, env_key, fallback_env)
        if required and not value:
            raise UserError(f"Missing configuration for {key}.")
        return value

    def _get_config_bool(
        self,
        key: str,
        env_key: str,
        *,
        fallback_env: str | None = None,
        default: bool,
    ) -> bool:
        value = self._get_config_raw_value(key, env_key, fallback_env)
        if not value:
            return default
        return self._to_bool(value)

    def _get_config_int(
        self,
        key: str,
        env_key: str,
        *,
        fallback_env: str | None = None,
        default: int,
    ) -> int:
        value = self._get_config_raw_value(key, env_key, fallback_env)
        if not value:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise UserError(f"Invalid integer for {key}.") from exc

    def _get_config_raw_value(self, key: str, env_key: str, fallback_env: str | None) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if not value and fallback_env:
            value = os.environ.get(fallback_env, "")
        return value

    # noinspection DuplicatedCode
    # Duplicated with RepairShopr importer to keep parsing local and avoid cross-addon coupling.
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
            return CmDataImporter._to_bool(decoded)
        if isinstance(value, (int, float)):
            return bool(value)
        value_str = str(value).strip().lower()
        return value_str in {"1", "true", "yes", "on", "y", "t"}

    @staticmethod
    def _write_if_changed(record: "odoo.model.transport_order", values: "odoo.values.transport_order") -> None:
        changes: "odoo.values.transport_order" = {}
        for field_name, value in values.items():
            if field_name not in record._fields:
                continue
            current_value = record[field_name]
            if isinstance(current_value, models.BaseModel):
                current_value = current_value.id
            if current_value != value:
                changes[field_name] = value
        if changes:
            record.write(changes)
