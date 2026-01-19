import logging
import os
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

IMPORT_CONTEXT: dict[str, bool] = {
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
        run_started_at = fields.Datetime.now()
        start_datetime = self._get_last_sync_at() if update_last_sync else None
        repairshopr_client = self._build_client()
        try:
            self._get_repairshopr_system()
            self._import_customers(repairshopr_client, start_datetime)
            self._import_products(repairshopr_client, start_datetime)
            self._import_tickets(repairshopr_client, start_datetime)
            self._import_estimates(repairshopr_client, start_datetime)
            self._import_invoices(repairshopr_client, start_datetime)
        except Exception as exc:
            _logger.exception("RepairShopr import failed")
            self._record_last_run("failed", str(exc))
            raise
        finally:
            repairshopr_client.clear_cache()

        self._record_last_run("success", "")
        if update_last_sync:
            self._set_last_sync_at(run_started_at)

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
            default=500,
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
