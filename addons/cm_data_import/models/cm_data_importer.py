import logging
import os
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.cm_data_client import (
    CmDataAccountName,
    CmDataClient,
    CmDataConnectionSettings,
    CmDataDeliveryLog,
    _to_bool as cm_data_to_bool,
)

_logger = logging.getLogger(__name__)

EXTERNAL_SYSTEM_CODE = "cm_data"
EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS = (
    "base.model_res_partner",
    "cm_transport.model_transport_order",
)

ACCOUNT_RESOURCE = "account"
CONTACT_RESOURCE = "contact"
DELIVERY_RESOURCE = "delivery_log"

IMPORT_CONTEXT: dict[str, bool] = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
}

STATUS_MAP = {
    "Pending": "ready",
    "Picked Up": "transit_in",
    "Delivered": "at_client",
    "Buybacks": "at_depot",
    "Cancelled": "draft",
    "Projected Return": "ready",
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
        try:
            self._get_cm_data_system()
            with CmDataClient(self._get_connection_settings()) as client:
                account_rows = client.fetch_account_names(updated_at=None)
                account_partner_map = self._import_accounts(account_rows)
                self._import_contacts(client, start_datetime, account_partner_map)
                self._import_delivery_logs(client, start_datetime, account_partner_map)
        except Exception as exc:
            _logger.exception("CM data import failed")
            self._record_last_run("failed", str(exc))
            raise

        self._record_last_run("success", "")
        if update_last_sync:
            self._set_last_sync_at(run_started_at)

    def _get_connection_settings(self) -> CmDataConnectionSettings:
        host = self._get_config_value(
            "cm_data.db.host",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__HOST",
            legacy_env_key="CM_DATA_DB_HOST",
        )
        user = self._get_config_value(
            "cm_data.db.user",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__USER",
            legacy_env_key="CM_DATA_DB_USER",
        )
        password = self._get_config_value(
            "cm_data.db.password",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__PASSWORD",
            legacy_env_key="CM_DATA_DB_PASSWORD",
        )
        database = self._get_config_value(
            "cm_data.db.name",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__NAME",
            legacy_env_key="CM_DATA_DB_NAME",
            required=False,
        )
        port = self._get_config_int(
            "cm_data.db.port",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__PORT",
            legacy_env_key="CM_DATA_DB_PORT",
            default=3306,
        )
        use_ssl = self._get_config_bool(
            "cm_data.db.use_ssl",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__USE_SSL",
            default=False,
        )
        ssl_verify = self._get_config_bool(
            "cm_data.db.ssl_verify",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__DB__SSL_VERIFY",
            default=True,
        )
        if not host or not user or not password:
            raise UserError("CM data connection settings are missing.")
        if not use_ssl:
            _logger.warning("CM data SSL disabled; enable for production.")
        if use_ssl and not ssl_verify:
            _logger.warning("CM data SSL verification disabled; enable for production.")
        return CmDataConnectionSettings(
            host=host,
            user=user,
            password=password,
            database=database or None,
            port=port,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
        )

    def _import_accounts(self, account_rows: list[CmDataAccountName]) -> dict[str, "odoo.model.res_partner"]:
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        partner_map: dict[str, "odoo.model.res_partner"] = {}
        for row in account_rows:
            values: "odoo.values.res_partner" = {
                "name": row.account_name,
                "cm_data_ticket_name": row.ticket_name,
                "cm_data_label_names": row.label_names,
                "cm_data_priority_flag": row.priority_flag,
                "cm_data_on_delivery_schedule": row.on_delivery_schedule,
                "cm_data_shipping_enable": row.shipping_enable,
                "cm_data_location_drop": row.location_drop,
            }
            partner = partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(row.record_id),
                values,
                resource=ACCOUNT_RESOURCE,
            )
            partner_map[self._normalize_key(row.account_name)] = partner
        return partner_map

    def _import_contacts(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> None:
        contacts = client.fetch_contacts(updated_at=start_datetime)
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        for row in contacts:
            key = self._normalize_key(row.account_name)
            parent_partner = partner_map.get(key)
            if not parent_partner:
                _logger.warning("Skipping contact without matching account: %s", row.account_name)
                continue
            name = row.sub_name or row.account_name
            values: "odoo.values.res_partner" = {
                "name": name,
                "parent_id": parent_partner.id,
                "type": "contact",
                "cm_data_contact_notes": row.contact_notes,
                "cm_data_contact_sort_order": row.sort_order,
            }
            partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(row.record_id),
                values,
                resource=CONTACT_RESOURCE,
            )

    def _import_delivery_logs(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> None:
        transport_model = self.env["transport.order"].sudo().with_context(IMPORT_CONTEXT)
        delivery_rows = client.fetch_delivery_logs(updated_at=start_datetime)
        for row in delivery_rows:
            client_partner = self._resolve_transport_partner(row, partner_map)
            employee_partner = self.env.user.partner_id
            state = self._map_transport_state(row.status)
            order_name = self._build_transport_order_name(row)
            values: "odoo.values.transport_order" = {
                "name": order_name,
                "state": state,
                "arrival_date": row.created_at,
                "scheduled_date": row.created_at,
                "departure_date": row.updated_at if row.updated_at and row.updated_at != row.created_at else False,
                "employee": employee_partner.id,
                "client": client_partner.id,
                "contact": client_partner.id,
                "quantity_in_counted": row.units,
                "cm_data_status_raw": row.status,
                "cm_data_location_name": row.location_name,
                "cm_data_location_id": row.location_id,
                "cm_data_units": row.units,
                "cm_data_notes": row.notes,
                "cm_data_edit_notes": row.edit_notes,
                "cm_data_ocr_notes": row.ocr_notes,
                "cm_data_discord_name": row.discord_name,
                "cm_data_discord_id": str(row.discord_id) if row.discord_id is not None else None,
            }
            transport_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(row.record_id),
                values,
                resource=DELIVERY_RESOURCE,
            )

    def _resolve_transport_partner(
        self,
        row: CmDataDeliveryLog,
        partner_map: dict[str, "odoo.model.res_partner"],
    ) -> "odoo.model.res_partner":
        normalized = self._normalize_key(row.location_name)
        partner = partner_map.get(normalized)
        if partner:
            return partner
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        existing_partner = partner_model.search([("name", "ilike", row.location_name)], limit=5)
        if existing_partner:
            exact_match = existing_partner.filtered(
                lambda record: self._normalize_key(record.name) == normalized
            )
            partner = exact_match[:1] or existing_partner[:1]
            partner_map[normalized] = partner
            return partner
        values: "odoo.values.res_partner" = {
            "name": row.location_name,
        }
        partner = partner_model.create(values)
        partner_map[normalized] = partner
        return partner

    @staticmethod
    def _map_transport_state(status: str) -> str:
        return STATUS_MAP.get(status, "draft")

    @staticmethod
    def _build_transport_order_name(row: CmDataDeliveryLog) -> str:
        location_name = (row.location_name or "").strip()
        if location_name:
            return location_name
        return f"Delivery Log {row.record_id}"

    def _get_cm_data_system(self) -> "odoo.model.external_system":
        return self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="CM Data",
            id_format=r"^\d+$",
            sequence=80,
            active=True,
            applicable_model_xml_ids=EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
        )

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
        legacy_env_key: str | None = None,
        required: bool = True,
    ) -> str:
        value = self._get_config_raw_value(key, env_key, legacy_env_key=legacy_env_key)
        if required and not value:
            raise UserError(f"Missing configuration for {key}.")
        return value

    def _get_config_bool(
        self,
        key: str,
        env_key: str,
        *,
        default: bool,
    ) -> bool:
        value = self._get_config_raw_value(key, env_key)
        if not value:
            return default
        return cm_data_to_bool(value)

    def _get_config_int(
        self,
        key: str,
        env_key: str,
        *,
        legacy_env_key: str | None = None,
        default: int,
    ) -> int:
        value = self._get_config_raw_value(key, env_key, legacy_env_key=legacy_env_key)
        if not value:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise UserError(f"Invalid integer for {key}.") from exc

    def _get_config_raw_value(
        self,
        key: str,
        env_key: str,
        *,
        legacy_env_key: str | None = None,
    ) -> str:
        parameter_model = self.env["ir.config_parameter"].sudo()
        value = parameter_model.get_param(key) or ""
        if not value:
            value = os.environ.get(env_key, "")
        if not value and legacy_env_key:
            value = os.environ.get(legacy_env_key, "")
        return value

    @staticmethod
    def _normalize_key(value: str | None) -> str:
        if not value:
            return ""
        return value.strip().casefold()
