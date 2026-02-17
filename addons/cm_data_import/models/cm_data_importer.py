import logging
import os
import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.transaction_utilities.models.cron_budget_mixin import CronRuntimeBudgetExceeded

from ..services.cm_data_client import (
    CmDataAccountName,
    CmDataClient,
    CmDataConnectionSettings,
    CmDataDirection,
    CmDataDeliveryLog,
    CmDataEmployee,
    CmDataNoteRow,
    CmDataPriceList,
    CmDataPricingCatalog,
    CmDataPricingLine,
    CmDataPtoUsage,
    CmDataTimeclockPunch,
    CmDataVacationUsage,
)
from ..services.cm_data_client import (
    _to_bool as cm_data_to_bool,
)

_logger = logging.getLogger(__name__)

EXTERNAL_SYSTEM_CODE = "cm_data"
EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS = (
    "base.model_res_partner",
    "hr.model_hr_employee",
    "hr_attendance.model_hr_attendance",
    "cm_transport.model_service_transport_order",
    "cm_quality_control.model_service_quality_control_checklist_item",
    "cm_data_import.model_integration_cm_data_direction",
    "cm_data_import.model_integration_cm_data_shipping_instruction",
    "cm_data_import.model_integration_cm_data_note",
    "cm_data_import.model_integration_cm_data_password",
    "cm_data_import.model_integration_cm_data_price_list",
    "cm_data_import.model_integration_cm_data_pricing_audit",
    "cm_data_import.model_integration_cm_data_pto_usage",
    "cm_data_import.model_integration_cm_data_vacation_usage",
    "cm_device.model_service_device_model",
    "cm_school.model_school_pricing_catalog",
    "cm_school.model_school_pricing_matrix",
)

ACCOUNT_RESOURCE = "account"
CONTACT_RESOURCE = "contact"
DELIVERY_RESOURCE = "delivery_log"
DIRECTION_RESOURCE = "direction"
SHIPPING_INSTRUCTION_RESOURCE = "shipping_instruction"
MODEL_NUMBER_RESOURCE = "model_number"
PRICE_LIST_RESOURCE = "price_list"
PRICING_CATALOG_RESOURCE = "pricing_catalog"
PRICING_LINE_RESOURCE = "pricing_line"
QUALITY_CONTROL_CHECKLIST_RESOURCE = "quality_control_checklist"
EMPLOYEE_RESOURCE = "employee"
PTO_USAGE_RESOURCE = "pto_usage"
VACATION_USAGE_RESOURCE = "vacation_usage"
TIMECLOCK_IN_RESOURCE = "timeclock_in"
TIMECLOCK_OUT_RESOURCE = "timeclock_out"
NOTE_TYPE_RESOURCES = {
    "intake": "intake",
    "diagnostic": "diagnostic",
    "repair": "repair",
    "quality_control": "quality_control",
    "invoice": "invoice",
}

IMPORT_CONTEXT = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
    "cm_skip_required_fields": True,
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
    _name = "integration.cm_data.importer"
    _description = "CM Data Importer"
    _inherit = ["transaction.cron_budget.mixin"]

    @api.model
    def run_scheduled_import(self) -> None:
        importer = self._with_cron_runtime_budget(job_name="CM Data Import")
        importer._run_import(update_last_sync=True)

    @api.model
    def run_full_import(self) -> None:
        self._run_import(update_last_sync=False)

    @api.model
    def _run_import(self, *, update_last_sync: bool) -> None:
        sync_started_at = fields.Datetime.now()
        use_last_sync_at = self._use_last_sync_at()
        start_datetime = self._get_last_sync_at() if update_last_sync and use_last_sync_at else None
        try:
            system = self._get_cm_data_system()
            with CmDataClient(self._get_connection_settings()) as client:
                price_list_rows = client.fetch_price_lists(updated_at=None)
                self._import_price_lists(price_list_rows, system, sync_started_at)
                account_rows = client.fetch_account_names(updated_at=None)
                account_partner_map = self._import_accounts(
                    account_rows,
                    system,
                    sync_started_at,
                )
                self._import_account_aliases(account_rows, account_partner_map)
                pricing_catalog_rows = client.fetch_pricing_catalogs(updated_at=None)
                pricing_line_rows = client.fetch_pricing_lines(updated_at=None)
                catalog_row_map, catalog_id_map = self._import_pricing_catalogs(
                    pricing_catalog_rows,
                    account_partner_map,
                    system,
                    sync_started_at,
                )
                self._import_pricing_lines(
                    pricing_line_rows,
                    catalog_row_map,
                    catalog_id_map,
                    system,
                    sync_started_at,
                )
                self._import_contacts(client, start_datetime, account_partner_map, system, sync_started_at)
                direction_rows = client.fetch_directions(updated_at=start_datetime)
                self._import_directions(
                    client,
                    start_datetime,
                    account_partner_map,
                    system,
                    sync_started_at,
                    direction_rows=direction_rows,
                )
                location_partner_map = self._build_location_partner_map(
                    account_rows,
                    direction_rows,
                    account_partner_map,
                )
                location_alias_partner_map = self._build_location_alias_partner_map(system)
                self._import_shipping_instructions(client, start_datetime, account_partner_map, system, sync_started_at)
                self._import_note_tables(client, None, account_partner_map, system, sync_started_at)
                self._import_passwords(client, None, account_partner_map)
                self._import_model_numbers(client, None, system, sync_started_at)
                self._import_delivery_logs(
                    client,
                    start_datetime,
                    account_partner_map,
                    location_partner_map,
                    location_alias_partner_map,
                    system,
                    sync_started_at,
                )
                employee_rows = client.fetch_employees(updated_at=None)
                employee_map, timeclock_employee_map = self._import_employees(employee_rows, system, sync_started_at)
                pto_rows = client.fetch_pto_usage(updated_at=None)
                self._import_pto_usage(pto_rows, employee_map, system, sync_started_at)
                vacation_rows = client.fetch_vacation_usage(updated_at=None)
                self._import_vacation_usage(vacation_rows, employee_map, system, sync_started_at)
                timeclock_rows = client.fetch_timeclock_punches(updated_at=None)
                self._import_timeclock_punches(timeclock_rows, timeclock_employee_map, system)
        except CronRuntimeBudgetExceeded as exception:
            message = str(exception)
            _logger.info(message)
            self._record_last_run("partial", message)
            return
        except Exception as exc:
            _logger.exception("CM data import failed")
            self._record_last_run("failed", str(exc))
            raise

        self._record_last_run("success", "")
        if update_last_sync and use_last_sync_at:
            self._set_last_sync_at(sync_started_at)

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

    def _import_accounts(
        self,
        account_rows: list[CmDataAccountName],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> dict[str, int]:
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        price_list_model = self.env["integration.cm_data.price.list"].sudo().with_context(IMPORT_CONTEXT)
        partner_role_map = self._build_partner_role_map()
        commit_interval = self._get_commit_interval()
        processed_count = 0
        partner_map: dict[str, int] = {}
        for row in account_rows:
            values: "odoo.values.res_partner" = {
                "name": row.account_name,
                "cm_data_ticket_name": row.ticket_name,
                "cm_data_ticket_name_report": row.ticket_name_report,
                "cm_data_label_names": row.label_names,
                "cm_data_multi_building_flag": row.multi_building_flag,
                "cm_data_priority_flag": row.priority_flag,
                "cm_data_on_delivery_schedule": row.on_delivery_schedule,
                "cm_data_shipping_enable": row.shipping_enable,
                "cm_data_location_drop": row.location_drop,
                "cm_data_price_list_ids": row.price_list,
                "cm_data_price_list_secondary_id": row.price_list_2,
            }
            partner = self._get_or_create_by_external_id_with_sync(
                partner_model,
                system,
                str(row.record_id),
                values,
                resource=ACCOUNT_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            if not partner:
                continue
            self._apply_partner_roles_from_labels(partner, row.label_names, partner_role_map)
            self._apply_partner_price_lists(partner, row.price_list, row.price_list_2, price_list_model)
            partner_map[self._normalize_key(row.account_name)] = partner.id
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="account"):
                partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
                price_list_model = self.env["integration.cm_data.price.list"].sudo().with_context(IMPORT_CONTEXT)
        return partner_map

    def _import_account_aliases(
        self,
        account_rows: list[CmDataAccountName],
        partner_map: dict[str, int],
    ) -> None:
        alias_model: "odoo.model.account_alias" = self.env["account.alias"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in account_rows:
            alias_values = self._extract_aliases(row.claim_name_list)
            if not alias_values:
                continue
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                continue
            for alias_value in alias_values:
                existing_alias = alias_model.search(
                    [
                        ("partner_id", "=", partner_id),
                        ("alias", "=", alias_value),
                        ("alias_type", "=", "claim"),
                    ],
                    limit=1,
                )
                if existing_alias:
                    continue
                alias_model.create(
                    {
                        "partner_id": partner_id,
                        "alias": alias_value,
                        "alias_type": "claim",
                        "active": True,
                    }
                )
                processed_count += 1
                if self._maybe_commit(processed_count, commit_interval, label="alias"):
                    alias_model = self.env["account.alias"].sudo().with_context(IMPORT_CONTEXT)

    def _import_contacts(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        contacts = client.fetch_contacts(updated_at=start_datetime)
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in contacts:
            key = self._normalize_key(row.account_name)
            parent_partner_id = partner_map.get(key)
            if not parent_partner_id:
                _logger.warning("Skipping contact without matching account: %s", row.account_name)
                continue
            name = row.sub_name or row.account_name
            values: "odoo.values.res_partner" = {
                "name": name,
                "parent_id": parent_partner_id,
                "type": "contact",
                "cm_data_contact_notes": row.contact_notes,
                "cm_data_contact_sort_order": row.sort_order,
            }
            self._get_or_create_by_external_id_with_sync(
                partner_model,
                system,
                str(row.record_id),
                values,
                resource=CONTACT_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="contact"):
                partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)

    def _import_directions(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
        *,
        direction_rows: list[CmDataDirection] | None = None,
    ) -> None:
        if direction_rows is None:
            direction_rows = client.fetch_directions(updated_at=start_datetime)
        direction_model = self.env["integration.cm_data.direction"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in direction_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                _logger.warning("Skipping direction without matching account: %s", row.account_name)
                continue
            name = row.ticket_title_name or row.school_name or row.account_name
            values: "odoo.values.integration_cm_data_direction" = {
                "name": name,
                "partner_id": partner_id,
                "ticket_title_name": row.ticket_title_name,
                "school_name": row.school_name,
                "delivery_day": row.delivery_day,
                "address": row.address,
                "directions": row.directions,
                "contact": row.contact,
                "priority": row.priority,
                "on_schedule_flag": row.on_schedule_flag,
                "delivery_order": row.delivery_order,
                "longitude": row.longitude,
                "latitude": row.latitude,
                "available_start": row.available_start,
                "available_end": row.available_end,
                "break_start": row.break_start,
                "break_end": row.break_end,
                "est_arrival_time": row.est_arrival_time,
                "shipping_enabled_flag": row.shipping_enabled_flag,
                "source_created_at": row.created_at,
                "source_updated_at": row.updated_at,
                "active": True,
            }
            self._get_or_create_by_external_id_with_sync(
                direction_model,
                system,
                str(row.record_id),
                values,
                resource=DIRECTION_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="direction"):
                direction_model = self.env["integration.cm_data.direction"].sudo().with_context(IMPORT_CONTEXT)

    def _import_shipping_instructions(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        instruction_rows = client.fetch_shipping_instructions(updated_at=start_datetime)
        instruction_model = self.env["integration.cm_data.shipping.instruction"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in instruction_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                _logger.warning("Skipping shipping instruction without matching account: %s", row.account_name)
                continue
            values: "odoo.values.integration_cm_data_shipping_instruction" = {
                "partner_id": partner_id,
                "address_key": row.address_key,
                "inbound_carrier": row.inbound_carrier,
                "inbound_service": row.inbound_service,
                "outbound_carrier": row.outbound_carrier,
                "outbound_service": row.outbound_service,
                "to_address_name": row.to_address_name,
                "to_address_company": row.to_address_company,
                "to_address_street1": row.to_address_street1,
                "to_address_street2": row.to_address_street2,
                "to_address_city": row.to_address_city,
                "to_address_state": row.to_address_state,
                "to_address_zip": row.to_address_zip,
                "to_address_country": row.to_address_country,
                "to_address_phone": row.to_address_phone,
                "to_address_email": row.to_address_email,
                "to_address_residential_flag": row.to_address_residential_flag,
                "parcel_length": row.parcel_length,
                "parcel_width": row.parcel_width,
                "parcel_height": row.parcel_height,
                "parcel_weight": row.parcel_weight,
                "options_print_custom_1": row.options_print_custom_1,
                "options_print_custom_2": row.options_print_custom_2,
                "options_label_format": row.options_label_format,
                "options_label_size": row.options_label_size,
                "options_hazmat": row.options_hazmat,
                "active": True,
            }
            self._get_or_create_by_external_id_with_sync(
                instruction_model,
                system,
                str(row.record_id),
                values,
                resource=SHIPPING_INSTRUCTION_RESOURCE,
                updated_at=None,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="shipping instruction"):
                instruction_model = self.env["integration.cm_data.shipping.instruction"].sudo().with_context(IMPORT_CONTEXT)

    def _import_note_tables(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        note_groups = [
            ("intake", client.fetch_intake_notes(updated_at=start_datetime)),
            ("diagnostic", client.fetch_diagnostic_notes(updated_at=start_datetime)),
            ("repair", client.fetch_repair_notes(updated_at=start_datetime)),
            ("quality_control", client.fetch_quality_control_notes(updated_at=start_datetime)),
            ("invoice", client.fetch_invoice_notes(updated_at=start_datetime)),
        ]
        for note_type, note_rows in note_groups:
            self._import_note_rows(note_rows, note_type, partner_map, system, sync_started_at)

    def _import_note_rows(
        self,
        note_rows: list[CmDataNoteRow],
        note_type: str,
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        note_model = self.env["integration.cm_data.note"].sudo().with_context(IMPORT_CONTEXT)
        checklist_item_model = self.env["service.quality.control.checklist.item"].sudo().with_context(
            IMPORT_CONTEXT
        )
        commit_interval = self._get_commit_interval()
        processed_count = 0
        resource = NOTE_TYPE_RESOURCES[note_type]
        for row in note_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                _logger.warning("Skipping %s note without matching account: %s", note_type, row.account_name)
                continue
            values: "odoo.values.integration_cm_data_note" = {
                "partner_id": partner_id,
                "note_type": note_type,
                "sub_name": row.sub_name,
                "notes": row.note,
                "sort_order": row.sort_order,
                "source_created_at": row.created_at,
                "source_updated_at": row.updated_at,
                "active": True,
            }
            self._get_or_create_by_external_id_with_sync(
                note_model,
                system,
                str(row.record_id),
                values,
                resource=resource,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            if note_type == "quality_control":
                self._import_quality_control_checklist_item(
                    checklist_item_model,
                    row,
                    partner_id,
                    system,
                    sync_started_at,
                )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label=f"{note_type} note"):
                note_model = self.env["integration.cm_data.note"].sudo().with_context(IMPORT_CONTEXT)
                checklist_item_model = self.env["service.quality.control.checklist.item"].sudo().with_context(
                    IMPORT_CONTEXT
                )

    def _import_quality_control_checklist_item(
        self,
        checklist_item_model: models.Model,
        note_row: CmDataNoteRow,
        partner_id: int,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        name = note_row.sub_name or "Quality Control"
        if not note_row.sub_name and note_row.note:
            first_line = note_row.note.splitlines()[0].strip()
            if first_line:
                name = first_line

        sequence = note_row.sort_order if note_row.sort_order is not None else 10
        values: "odoo.values.service_quality_control_checklist_item" = {
            "name": name,
            "partner_id": partner_id,
            "category": "other",
            "description": note_row.note,
            "sequence": sequence,
            "active": True,
        }
        self._get_or_create_by_external_id_with_sync(
            checklist_item_model,
            system,
            str(note_row.record_id),
            values,
            resource=QUALITY_CONTROL_CHECKLIST_RESOURCE,
            updated_at=note_row.updated_at,
            sync_started_at=sync_started_at,
        )

    def _import_passwords(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
    ) -> None:
        password_rows = client.fetch_passwords(updated_at=start_datetime)
        password_model = self.env["integration.cm_data.password"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in password_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                _logger.warning("Skipping password without matching account: %s", row.account_name)
                continue
            values: "odoo.values.integration_cm_data_password" = {
                "partner_id": partner_id,
                "sub_name": row.sub_name,
                "user_name": row.user_name,
                "password": self._mask_password(row.password),
                "notes": row.notes,
                "source_created_at": row.created_at,
                "source_updated_at": row.updated_at,
                "active": True,
            }
            existing_password = password_model.search(
                [
                    ("partner_id", "=", partner_id),
                    ("sub_name", "=", row.sub_name or False),
                    ("user_name", "=", row.user_name or False),
                ],
                limit=1,
            )
            if existing_password:
                existing_password.write(values)
            else:
                password_model.create(values)
            processed_count += 1
            # noinspection PyUnresolvedReferences
            # False positive: helper is defined later in this class.
            if self._maybe_commit(processed_count, commit_interval, label="password"):
                password_model = self.env["integration.cm_data.password"].sudo().with_context(IMPORT_CONTEXT)

    def _import_price_lists(
        self,
        price_list_rows: list[CmDataPriceList],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        price_list_model = self.env["integration.cm_data.price.list"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in price_list_rows:
            values: "odoo.values.integration_cm_data_price_list" = {
                "name": row.link or f"Price List {row.record_id}",
                "link": row.link,
                "source_created_at": row.created_at,
                "source_updated_at": row.updated_at,
                "active": True,
            }
            self._get_or_create_by_external_id_with_sync(
                price_list_model,
                system,
                str(row.record_id),
                values,
                resource=PRICE_LIST_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="price list"):
                price_list_model = self.env["integration.cm_data.price.list"].sudo().with_context(IMPORT_CONTEXT)

    def _import_pricing_catalogs(
        self,
        catalog_rows: list[CmDataPricingCatalog],
        partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> tuple[dict[int, CmDataPricingCatalog], dict[int, int]]:
        catalog_model_name = "school.pricing.catalog"
        catalog_model = self.env[catalog_model_name].sudo().with_context(IMPORT_CONTEXT)
        audit_model = self.env["integration.cm_data.pricing.audit"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        catalog_row_map: dict[int, CmDataPricingCatalog] = {row.record_id: row for row in catalog_rows}
        catalog_id_map: dict[int, int] = {}
        for row in catalog_rows:
            if row.code == "regular":
                continue
            partner, issue_type = self._resolve_pricing_partner(row.partner_label, partner_map)
            if issue_type:
                self._create_pricing_audit(
                    audit_model,
                    issue_type=issue_type,
                    catalog_code=row.code,
                    catalog_name=row.name,
                    partner=partner,
                    source_catalog_id=row.record_id,
                    message=f"Pricing catalog '{row.name}' partner label '{row.partner_label}' could not be linked to a partner.",
                )
                continue
            # noinspection PyUnresolvedReferences
            # False positive: fields are provided by the cm_school dependency.
            values: "odoo.values.school_pricing_catalog" = {
                "name": row.name,
                "code": row.code,
                "partner_id": partner.id if partner else False,
                "notes": row.notes,
                "active": row.active,
            }
            # noinspection PyTypeChecker
            # False positive: cm_school catalog inherits external.id.mixin at runtime.
            catalog_record = self._get_or_create_by_external_id_with_sync(
                catalog_model,
                system,
                row.code,
                values,
                resource=PRICING_CATALOG_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            catalog_id_map[row.record_id] = catalog_record.id
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="pricing catalog"):
                catalog_model = self.env[catalog_model_name].sudo().with_context(IMPORT_CONTEXT)
                audit_model = self.env["integration.cm_data.pricing.audit"].sudo().with_context(IMPORT_CONTEXT)
        return catalog_row_map, catalog_id_map

    def _import_pricing_lines(
        self,
        line_rows: list[CmDataPricingLine],
        catalog_row_map: dict[int, CmDataPricingCatalog],
        catalog_id_map: dict[int, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        matrix_model = self.env["school.pricing.matrix"].sudo().with_context(IMPORT_CONTEXT)
        audit_model = self.env["integration.cm_data.pricing.audit"].sudo().with_context(IMPORT_CONTEXT)
        currency_model = self.env["res.currency"].sudo()
        product_name_map = self._build_product_name_map()
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in line_rows:
            catalog_row = catalog_row_map.get(row.catalog_id)
            if not catalog_row:
                self._create_pricing_audit(
                    audit_model,
                    issue_type="missing_catalog",
                    model_label=row.model_label,
                    repair_label=row.repair_label,
                    source_price=row.price,
                    source_catalog_id=row.catalog_id,
                    source_line_id=row.record_id,
                    message="Pricing line references an unknown catalog.",
                )
                continue
            if catalog_row.code == "regular":
                self._audit_regular_pricing(
                    audit_model,
                    catalog_row,
                    row,
                    product_name_map,
                    currency_model,
                )
                continue
            catalog_record_id = catalog_id_map.get(row.catalog_id)
            if not catalog_record_id:
                self._create_pricing_audit(
                    audit_model,
                    issue_type="missing_catalog",
                    catalog_code=catalog_row.code,
                    catalog_name=catalog_row.name,
                    model_label=row.model_label,
                    repair_label=row.repair_label,
                    source_price=row.price,
                    source_batch=row.source_batch,
                    source_file=row.source_file,
                    source_catalog_id=row.catalog_id,
                    source_line_id=row.record_id,
                    message="Pricing catalog is missing for this line.",
                )
                continue
            # noinspection PyUnresolvedReferences
            # False positive: fields are provided by the cm_school dependency.
            values: "odoo.values.school_pricing_matrix" = {
                "name": f"{row.model_label} - {row.repair_label}",
                "catalog_id": catalog_record_id,
                "model_label": row.model_label,
                "repair_label": row.repair_label,
                "price": row.price,
                "active": row.active,
            }
            # noinspection PyTypeChecker
            # False positive: cm_school matrix inherits external.id.mixin at runtime.
            self._get_or_create_by_external_id_with_sync(
                matrix_model,
                system,
                str(row.record_id),
                values,
                resource=PRICING_LINE_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="pricing line"):
                matrix_model = self.env["school.pricing.matrix"].sudo().with_context(IMPORT_CONTEXT)
                audit_model = self.env["integration.cm_data.pricing.audit"].sudo().with_context(IMPORT_CONTEXT)

    def _resolve_pricing_partner(
        self,
        partner_label: str | None,
        partner_map: dict[str, int],
    ) -> tuple["odoo.model.res_partner | None", str | None]:
        if not partner_label:
            return None, "missing_partner"
        normalized_label = self._normalize_key(partner_label)
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        alias_model: "odoo.model.account_alias" = self.env["account.alias"].sudo().with_context(IMPORT_CONTEXT)

        partner_id = partner_map.get(normalized_label)
        if partner_id:
            partner = partner_model.browse(partner_id).exists()
            if partner:
                return partner.commercial_partner_id, None

        alias_matches = alias_model.search(
            [
                ("alias", "ilike", partner_label),
                ("alias_type", "=", "account"),
                ("active", "=", True),
            ],
            limit=5,
        )
        exact_aliases = alias_matches.filtered(lambda record: self._normalize_key(record.alias) == normalized_label)
        if len(exact_aliases) == 1:
            return exact_aliases.partner_id.commercial_partner_id, None
        if len(exact_aliases) > 1:
            return None, "ambiguous_partner"

        partner_matches = partner_model.search([("name", "ilike", partner_label)], limit=5)
        exact_matches = partner_matches.filtered(lambda record: self._normalize_key(record.name) == normalized_label)
        if len(exact_matches) == 1:
            return exact_matches[0].commercial_partner_id, None
        if len(exact_matches) > 1:
            return None, "ambiguous_partner"
        return None, "missing_partner"

    def _resolve_pricing_currency(
        self,
        currency_model: "odoo.model.res_currency",
        currency_code: str | None,
    ) -> "odoo.model.res_currency":
        if currency_code:
            currency = currency_model.search([("name", "=", currency_code)], limit=1)
            if currency:
                return currency
        return self.env.company.currency_id

    def _build_product_name_map(self) -> dict[str, list["odoo.model.product_template"]]:
        product_model = self.env["product.template"].sudo().with_context(IMPORT_CONTEXT)
        product_records = product_model.search([])
        name_map: dict[str, list["odoo.model.product_template"]] = {}
        for product in product_records:
            normalized = self._normalize_key(product.name)
            if not normalized:
                continue
            name_map.setdefault(normalized, []).append(product)
        return name_map

    def _audit_regular_pricing(
        self,
        audit_model: "odoo.model.integration_cm_data_pricing_audit",
        catalog_row: CmDataPricingCatalog,
        line_row: CmDataPricingLine,
        product_name_map: dict[str, list["odoo.model.product_template"]],
        currency_model: "odoo.model.res_currency",
    ) -> None:
        normalized_repair = self._normalize_key(line_row.repair_label)
        if not normalized_repair:
            return
        product_candidates = product_name_map.get(normalized_repair, [])
        if not product_candidates:
            self._create_pricing_audit(
                audit_model,
                issue_type="missing_product",
                catalog_code=catalog_row.code,
                catalog_name=catalog_row.name,
                model_label=line_row.model_label,
                repair_label=line_row.repair_label,
                source_price=line_row.price,
                source_batch=line_row.source_batch,
                source_file=line_row.source_file,
                source_catalog_id=line_row.catalog_id,
                source_line_id=line_row.record_id,
                message="Regular pricing row has no matching product by name.",
            )
            return
        if len(product_candidates) > 1:
            product_names = ", ".join(sorted({product.display_name for product in product_candidates}))
            self._create_pricing_audit(
                audit_model,
                issue_type="multiple_products",
                catalog_code=catalog_row.code,
                catalog_name=catalog_row.name,
                model_label=line_row.model_label,
                repair_label=line_row.repair_label,
                source_price=line_row.price,
                source_batch=line_row.source_batch,
                source_file=line_row.source_file,
                source_catalog_id=line_row.catalog_id,
                source_line_id=line_row.record_id,
                message=f"Multiple products match repair label: {product_names}.",
            )
            return
        product = product_candidates[0]
        currency = self._resolve_pricing_currency(currency_model, line_row.currency)
        if line_row.price is None:
            return
        if abs(product.list_price - line_row.price) > 0.01:
            self._create_pricing_audit(
                audit_model,
                issue_type="price_mismatch",
                catalog_code=catalog_row.code,
                catalog_name=catalog_row.name,
                product=product,
                model_label=line_row.model_label,
                repair_label=line_row.repair_label,
                source_price=line_row.price,
                product_price=product.list_price,
                currency=currency,
                source_batch=line_row.source_batch,
                source_file=line_row.source_file,
                source_catalog_id=line_row.catalog_id,
                source_line_id=line_row.record_id,
                message="Regular pricing does not match product list price.",
            )

    @staticmethod
    def _create_pricing_audit(
        audit_model: "odoo.model.integration_cm_data_pricing_audit",
        *,
        issue_type: str,
        catalog: models.Model | None = None,
        catalog_code: str | None = None,
        catalog_name: str | None = None,
        partner: "odoo.model.res_partner | None" = None,
        product: "odoo.model.product_template | None" = None,
        model_label: str | None = None,
        repair_label: str | None = None,
        source_price: float | None = None,
        product_price: float | None = None,
        currency: "odoo.model.res_currency | None" = None,
        source_batch: str | None = None,
        source_file: str | None = None,
        source_catalog_id: int | None = None,
        source_line_id: int | None = None,
        message: str | None = None,
    ) -> None:
        values: "odoo.values.integration_cm_data_pricing_audit" = {
            "catalog_id": catalog.id if catalog else False,
            "catalog_code": catalog_code,
            "catalog_name": catalog_name,
            "partner_id": partner.id if partner else False,
            "product_id": product.id if product else False,
            "issue_type": issue_type,
            "model_label": model_label,
            "repair_label": repair_label,
            "source_price": source_price,
            "product_price": product_price,
            "currency_id": currency.id if currency else False,
            "source_batch": source_batch,
            "source_file": source_file,
            "source_catalog_id": source_catalog_id,
            "source_line_id": source_line_id,
            "message": message,
        }
        audit_model.create(values)

    def _import_model_numbers(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        model_rows = client.fetch_model_numbers(updated_at=start_datetime)
        device_model = self.env["service.device.model"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in model_rows:
            values: "odoo.values.service_device_model" = {
                "number": row.model,
            }
            self._get_or_create_by_external_id_with_sync(
                device_model,
                system,
                str(row.record_id),
                values,
                resource=MODEL_NUMBER_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="model number"):
                device_model = self.env["service.device.model"].sudo().with_context(IMPORT_CONTEXT)

    def _import_delivery_logs(
        self,
        client: CmDataClient,
        start_datetime: datetime | None,
        partner_map: dict[str, int],
        location_partner_map: dict[str, int],
        location_alias_partner_map: dict[str, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        transport_model = self.env["service.transport.order"].sudo().with_context(IMPORT_CONTEXT)
        delivery_rows = client.fetch_delivery_logs(updated_at=start_datetime)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        unmatched_locations: dict[str, int] = {}
        for row in delivery_rows:
            client_partner = self._resolve_transport_partner(
                row,
                partner_map,
                location_partner_map,
                location_alias_partner_map,
                unmatched_locations,
            )
            employee_partner = self.env.user.partner_id
            state = self._map_transport_state(row.status)
            order_name = self._build_transport_order_name(row)
            values: "odoo.values.service_transport_order" = {
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
            self._get_or_create_by_external_id_with_sync(
                transport_model,
                system,
                str(row.record_id),
                values,
                resource=DELIVERY_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="delivery"):
                transport_model = self.env["service.transport.order"].sudo().with_context(IMPORT_CONTEXT)
        self._log_unmatched_transport_locations(unmatched_locations)

    def _import_employees(
        self,
        employee_rows: list[CmDataEmployee],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> tuple[dict[int, int], dict[int, int]]:
        employee_model = self.env["hr.employee"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        employee_map: dict[int, int] = {}
        timeclock_employee_map: dict[int, int] = {}
        for row in employee_rows:
            first_name, last_name, nick_name = self._split_employee_name_parts(row)
            display_name = " ".join(part for part in [first_name, last_name] if part).strip()
            if not display_name:
                display_name = nick_name or f"Employee {row.record_id}"
            values: dict[str, object] = {
                "name": display_name,
            }
            if "first_name" in employee_model._fields:
                values["first_name"] = first_name
            if "last_name" in employee_model._fields:
                values["last_name"] = last_name
            if "nick_name" in employee_model._fields:
                values["nick_name"] = nick_name
            if "active" in employee_model._fields:
                values["active"] = row.active
            if "work_email" in employee_model._fields:
                work_email = self._extract_email(row.grafana_username)
                if work_email:
                    values["work_email"] = work_email
            if "cm_data_timeclock_id" in employee_model._fields:
                values["cm_data_timeclock_id"] = row.timeclock_id
            if "cm_data_repairshopr_id" in employee_model._fields:
                values["cm_data_repairshopr_id"] = row.repairshopr_id
            if "cm_data_discord_id" in employee_model._fields:
                values["cm_data_discord_id"] = str(row.discord_id) if row.discord_id is not None else None
            if "cm_data_grafana_username" in employee_model._fields:
                values["cm_data_grafana_username"] = row.grafana_username
            if "cm_data_dept" in employee_model._fields:
                values["cm_data_dept"] = row.dept
            if "cm_data_team" in employee_model._fields:
                values["cm_data_team"] = row.team
            if "cm_data_on_site" in employee_model._fields:
                values["cm_data_on_site"] = row.on_site
            if "cm_data_last_day" in employee_model._fields and row.last_day:
                values["cm_data_last_day"] = self._as_date(row.last_day)
            if "birthday" in employee_model._fields and row.date_of_birth:
                values["birthday"] = self._as_date(row.date_of_birth)
            if "first_contract_date" in employee_model._fields and row.date_of_hire:
                values["first_contract_date"] = self._as_date(row.date_of_hire)
            employee_record = self._get_or_create_by_external_id_with_sync(
                employee_model,
                system,
                str(row.record_id),
                values,
                resource=EMPLOYEE_RESOURCE,
                updated_at=None,
                sync_started_at=sync_started_at,
            )
            if employee_record:
                employee_map[row.record_id] = employee_record.id
                if row.timeclock_id:
                    timeclock_employee_map[row.timeclock_id] = employee_record.id
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="employee"):
                employee_model = self.env["hr.employee"].sudo().with_context(IMPORT_CONTEXT)
        return employee_map, timeclock_employee_map

    def _import_pto_usage(
        self,
        usage_rows: list[CmDataPtoUsage],
        employee_map: dict[int, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        usage_model = self.env["integration.cm_data.pto.usage"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in usage_rows:
            employee_id = employee_map.get(row.employee_id or 0)
            values: "odoo.values.integration_cm_data_pto_usage" = {
                "employee_id": employee_id or False,
                "used_at": row.used_at,
                "pay_period_ending": self._as_date(row.pay_period_ending),
                "usage_hours": float(row.usage or 0.0),
                "notes": row.notes,
                "added_by": row.added_by,
                "source_updated_at": row.updated_at,
            }
            self._get_or_create_by_external_id_with_sync(
                usage_model,
                system,
                str(row.record_id),
                values,
                resource=PTO_USAGE_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="pto usage"):
                usage_model = self.env["integration.cm_data.pto.usage"].sudo().with_context(IMPORT_CONTEXT)

    def _import_vacation_usage(
        self,
        usage_rows: list[CmDataVacationUsage],
        employee_map: dict[int, int],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        usage_model = self.env["integration.cm_data.vacation.usage"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for row in usage_rows:
            employee_id = employee_map.get(row.employee_id or 0)
            values: "odoo.values.integration_cm_data_vacation_usage" = {
                "employee_id": employee_id or False,
                "date_of": self._as_date(row.date_of),
                "usage_hours": float(row.usage_hours or 0.0),
                "notes": row.notes,
                "added_by": row.added_by,
                "source_created_at": row.created_at,
                "source_updated_at": row.updated_at,
            }
            self._get_or_create_by_external_id_with_sync(
                usage_model,
                system,
                str(row.record_id),
                values,
                resource=VACATION_USAGE_RESOURCE,
                updated_at=row.updated_at,
                sync_started_at=sync_started_at,
            )
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="vacation usage"):
                usage_model = self.env["integration.cm_data.vacation.usage"].sudo().with_context(IMPORT_CONTEXT)

    def _import_timeclock_punches(
        self,
        punch_rows: list[CmDataTimeclockPunch],
        timeclock_employee_map: dict[int, int],
        system: "odoo.model.external_system",
    ) -> None:
        attendance_model = self.env["hr.attendance"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        closing_time = self._get_timeclock_close_time()
        today_local = fields.Date.context_today(self)
        employee_ids = {
            employee_id for employee_id in (timeclock_employee_map.get(row.user_id or 0) for row in punch_rows) if employee_id
        }
        open_attendance_by_employee: dict[int, int] = {}
        if employee_ids:
            open_attendance_records = attendance_model.search(
                [
                    ("employee_id", "in", list(employee_ids)),
                    ("check_out", "=", False),
                ],
                order="check_in desc, id desc",
            )
            for attendance in open_attendance_records:
                employee_id = attendance.employee_id.id
                if employee_id not in open_attendance_by_employee:
                    open_attendance_by_employee[employee_id] = attendance.id

        def punch_sort_key(punch: CmDataTimeclockPunch) -> tuple[int, datetime, int]:
            employee_id = timeclock_employee_map.get(punch.user_id or 0) or 0
            sort_time = self._resolve_punch_time(punch) or datetime.min
            return employee_id, sort_time, punch.record_id

        for row in sorted(punch_rows, key=punch_sort_key):
            employee_id = timeclock_employee_map.get(row.user_id or 0)
            if not employee_id:
                _logger.warning("Timeclock punch %s has no mapped employee; skipping.", row.record_id)
                continue
            punch_time = self._resolve_punch_time(row)
            if not punch_time:
                _logger.warning("Timeclock punch %s has no timestamp; skipping.", row.record_id)
                continue
            punch_kind = self._classify_timeclock_check_type(row.check_type)
            if not punch_kind:
                punch_kind = "out" if employee_id in open_attendance_by_employee else "in"
            resource = TIMECLOCK_IN_RESOURCE if punch_kind == "in" else TIMECLOCK_OUT_RESOURCE
            updated_at = self._resolve_punch_updated_at(row) or punch_time
            external_id_value = str(row.record_id)
            if not self._should_process_external_row(system, external_id_value, resource, updated_at):
                continue

            attendance_record = attendance_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                resource,
            )
            if attendance_record and attendance_record.exists():
                if punch_kind == "in":
                    values: "odoo.values.hr_attendance" = {
                        "employee_id": employee_id,
                        "check_in": punch_time,
                    }
                    attendance_record.write(values)
                    if attendance_record.check_out and attendance_record.check_out < punch_time:
                        attendance_record.write({"check_out": punch_time})
                    if attendance_record.check_out:
                        open_attendance_by_employee.pop(employee_id, None)
                    else:
                        open_attendance_by_employee[employee_id] = attendance_record.id
                else:
                    check_out_time = punch_time
                    if attendance_record.check_in and check_out_time < attendance_record.check_in:
                        check_out_time = attendance_record.check_in
                    if attendance_record.check_out != check_out_time:
                        values: "odoo.values.hr_attendance" = {
                            "check_out": check_out_time,
                        }
                        attendance_record.write(values)
                    open_attendance_by_employee.pop(employee_id, None)
                self._mark_external_id_synced(system, external_id_value, resource, updated_at)
                processed_count += 1
                if self._maybe_commit(processed_count, commit_interval, label="attendance"):
                    attendance_model = self.env["hr.attendance"].sudo().with_context(IMPORT_CONTEXT)
                continue

            if punch_kind == "in":
                open_attendance_id = open_attendance_by_employee.get(employee_id)
                if open_attendance_id:
                    open_attendance = attendance_model.browse(open_attendance_id).exists()
                    if open_attendance and not open_attendance.check_out:
                        check_in_local = self._to_local_datetime(open_attendance.check_in)
                        punch_local = self._to_local_datetime(punch_time)
                        if punch_local.date() > check_in_local.date() or punch_local.time() > closing_time:
                            self._close_attendance_missing_checkout(
                                open_attendance,
                                closing_time=closing_time,
                                reason=f"missing_checkout_before_new_check_in punch={row.record_id}",
                            )
                        else:
                            check_out_time = punch_time
                            if open_attendance.check_in and check_out_time < open_attendance.check_in:
                                check_out_time = open_attendance.check_in
                            try:
                                open_attendance.write({"check_out": check_out_time})
                            except ValidationError:
                                self._close_attendance_with_check_out(
                                    open_attendance,
                                    check_out_time=check_out_time,
                                    reason=f"missing_checkout_before_new_check_in punch={row.record_id}",
                                )
                    open_attendance_by_employee.pop(employee_id, None)
                values: "odoo.values.hr_attendance" = {
                    "employee_id": employee_id,
                    "check_in": punch_time,
                }
                attendance_record = self._create_attendance_with_fix(
                    attendance_model,
                    values,
                    employee_id=employee_id,
                    closing_time=closing_time,
                    reason=f"missing_checkout_on_check_in punch={row.record_id}",
                )
                if attendance_record.check_out:
                    open_attendance_by_employee.pop(employee_id, None)
                else:
                    open_attendance_by_employee[employee_id] = attendance_record.id
            else:
                open_attendance_id = open_attendance_by_employee.get(employee_id)
                open_attendance = (
                    attendance_model.browse(open_attendance_id).exists() if open_attendance_id else attendance_model.browse()
                )
                if not open_attendance:
                    open_attendance = attendance_model.search(
                        [
                            ("employee_id", "=", employee_id),
                            ("check_out", "=", False),
                        ],
                        order="check_in desc, id desc",
                        limit=1,
                    )
                if open_attendance:
                    check_out_time = punch_time
                    if open_attendance.check_in and check_out_time < open_attendance.check_in:
                        check_out_time = open_attendance.check_in
                    try:
                        open_attendance.write({"check_out": check_out_time})
                    except ValidationError:
                        self._close_attendance_with_check_out(
                            open_attendance,
                            check_out_time=check_out_time,
                            reason=f"missing_checkout_on_check_out punch={row.record_id}",
                        )
                    attendance_record = open_attendance
                else:
                    values: "odoo.values.hr_attendance" = {
                        "employee_id": employee_id,
                        "check_in": punch_time,
                        "check_out": punch_time,
                    }
                    attendance_record = self._create_attendance_with_fix(
                        attendance_model,
                        values,
                        employee_id=employee_id,
                        closing_time=closing_time,
                        reason=f"missing_checkout_on_check_out punch={row.record_id}",
                    )
                open_attendance_by_employee.pop(employee_id, None)

            attendance_record.set_external_id(EXTERNAL_SYSTEM_CODE, external_id_value, resource)
            self._mark_external_id_synced(system, external_id_value, resource, updated_at)
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="attendance"):
                attendance_model = self.env["hr.attendance"].sudo().with_context(IMPORT_CONTEXT)

        for employee_id, attendance_id in list(open_attendance_by_employee.items()):
            attendance = attendance_model.browse(attendance_id).exists()
            if not attendance or attendance.check_out:
                continue
            check_in_local = self._to_local_datetime(attendance.check_in)
            if check_in_local.date() >= today_local:
                continue
            self._close_attendance_missing_checkout(
                attendance,
                closing_time=closing_time,
                reason="missing_checkout_end_of_import",
            )

    def _resolve_transport_partner(
        self,
        row: CmDataDeliveryLog,
        partner_map: dict[str, int],
        location_partner_map: dict[str, int],
        location_alias_partner_map: dict[str, int],
        unmatched_locations: dict[str, int],
    ) -> "odoo.model.res_partner":
        normalized = self._normalize_key(row.location_name)
        partner_id = location_partner_map.get(normalized) or location_alias_partner_map.get(normalized)
        if not partner_id:
            partner_id = partner_map.get(normalized)
        if partner_id:
            return self.env["res.partner"].sudo().browse(partner_id)
        raw_location = (row.location_name or "").strip()
        if raw_location:
            unmatched_locations[raw_location] = unmatched_locations.get(raw_location, 0) + 1
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        existing_partner = partner_model.search([("name", "ilike", row.location_name)], limit=5)
        if existing_partner:
            exact_match = existing_partner.filtered(lambda record: self._normalize_key(record.name) == normalized)
            partner = exact_match[:1] or existing_partner[:1]
            partner_map[normalized] = partner.id
            return partner
        values: "odoo.values.res_partner" = {
            "name": row.location_name,
        }
        partner = partner_model.create(values)
        partner_map[normalized] = partner.id
        return partner

    def _log_unmatched_transport_locations(self, unmatched_locations: dict[str, int]) -> None:
        if not unmatched_locations:
            return
        sorted_locations = sorted(
            unmatched_locations.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
        top_locations = ", ".join(
            f"{name} ({count})" for name, count in sorted_locations[:25]
        )
        _logger.warning(
            "CM delivery locations missing account mapping (top %s of %s): %s",
            min(25, len(sorted_locations)),
            len(sorted_locations),
            top_locations,
        )

    def _build_location_partner_map(
        self,
        account_rows: list[CmDataAccountName],
        direction_rows: list[CmDataDirection],
        partner_map: dict[str, int],
    ) -> dict[str, int]:
        location_partner_map: dict[str, int] = {}
        for row in account_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                continue
            for token in (row.account_name, row.ticket_name, row.ticket_name_report):
                normalized = self._normalize_key(token)
                if normalized and normalized not in location_partner_map:
                    location_partner_map[normalized] = partner_id
        for row in direction_rows:
            partner_id = partner_map.get(self._normalize_key(row.account_name))
            if not partner_id:
                continue
            for token in (row.ticket_title_name, row.school_name, row.account_name):
                normalized = self._normalize_key(token)
                if normalized and normalized not in location_partner_map:
                    location_partner_map[normalized] = partner_id
        return location_partner_map

    def _build_location_alias_partner_map(
        self,
        system: "odoo.model.external_system",
    ) -> dict[str, int]:
        if "school.location.option.alias" not in self.env:
            return {}
        alias_model = self.env["school.location.option.alias"].sudo().with_context(IMPORT_CONTEXT)
        alias_map: dict[str, int] = {}
        for alias in alias_model.search([("system_id", "=", system.id)]):
            normalized = self._normalize_key(alias.external_key)
            if not normalized:
                continue
            partner = alias.location_option_id.partner_id
            if not partner:
                continue
            alias_map.setdefault(normalized, partner.id)
        return alias_map

    @staticmethod
    def _map_transport_state(status: str) -> str:
        return STATUS_MAP.get(status, "draft")

    @staticmethod
    def _build_transport_order_name(row: CmDataDeliveryLog) -> str:
        location_name = (row.location_name or "").strip()
        if location_name:
            return location_name
        return f"Delivery Log {row.record_id}"

    def _build_partner_role_map(self) -> dict[str, int]:
        role_model = self.env["school.partner.role"].sudo()
        role_map: dict[str, int] = {}
        for role in role_model.search([]):
            for token in (role.code, role.name):
                normalized = self._normalize_key(token)
                if normalized and normalized not in role_map:
                    role_map[normalized] = role.id
        return role_map

    def _apply_partner_roles_from_labels(
        self,
        partner: "odoo.model.res_partner",
        label_names: str | None,
        partner_role_map: dict[str, int],
    ) -> None:
        if "partner_role_ids" not in partner._fields:
            return
        role_ids = self._resolve_partner_role_ids(label_names, partner_role_map)
        if not role_ids:
            return
        current_ids = partner.partner_role_ids.ids
        merged_ids = sorted(set(current_ids).union(role_ids))
        if set(current_ids) != set(merged_ids):
            partner.write({"partner_role_ids": [(6, 0, merged_ids)]})

    def _resolve_partner_role_ids(self, label_names: str | None, partner_role_map: dict[str, int]) -> list[int]:
        tokens = self._extract_aliases(label_names)
        role_ids: list[int] = []
        for token in tokens:
            normalized = self._normalize_key(token)
            role_id = partner_role_map.get(normalized)
            if role_id:
                role_ids.append(role_id)
            else:
                _logger.warning("CM data label '%s' did not match a partner role.", token)
        return list(dict.fromkeys(role_ids))

    def _apply_partner_price_lists(
        self,
        partner: "odoo.model.res_partner",
        primary_value: str | None,
        secondary_value: str | None,
        price_list_model: "odoo.model.integration_cm_data_price_list",
    ) -> None:
        if "cm_data_price_list_record_ids" not in partner._fields:
            return
        primary_ids = self._parse_cm_id_list(primary_value)
        secondary_ids = self._parse_cm_id_list(secondary_value)
        external_ids = list(dict.fromkeys([*primary_ids, *secondary_ids]))
        if not external_ids and not secondary_ids:
            return
        record_ids = self._resolve_price_list_record_ids(price_list_model, external_ids)
        if record_ids:
            current_ids = partner.cm_data_price_list_record_ids.ids
            merged_ids = sorted(set(current_ids).union(record_ids))
            if set(current_ids) != set(merged_ids):
                partner.write({"cm_data_price_list_record_ids": [(6, 0, merged_ids)]})
        if secondary_ids and "cm_data_price_list_secondary_record_id" in partner._fields:
            secondary_records = self._resolve_price_list_record_ids(price_list_model, secondary_ids)
            if secondary_records:
                secondary_id = secondary_records[0]
                if partner.cm_data_price_list_secondary_record_id.id != secondary_id:
                    partner.write({"cm_data_price_list_secondary_record_id": secondary_id})

    def _parse_cm_id_list(self, value: str | None) -> list[str]:
        tokens = self._extract_aliases(value)
        id_values: list[str] = []
        for token in tokens:
            match = re.search(r"\d+", token)
            if not match:
                _logger.info("CM data value '%s' did not include an id; skipping.", token)
                continue
            id_values.append(match.group(0))
        return list(dict.fromkeys(id_values))

    def _resolve_price_list_record_ids(
        self,
        price_list_model: "odoo.model.integration_cm_data_price_list",
        external_ids: list[str],
    ) -> list[int]:
        record_ids: list[int] = []
        for external_id in external_ids:
            record = price_list_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id,
                PRICE_LIST_RESOURCE,
            )
            if not record:
                _logger.warning("CM data price list '%s' not found; skipping.", external_id)
                continue
            record_ids.append(record.id)
        return list(dict.fromkeys(record_ids))

    @staticmethod
    def _extract_aliases(raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        tokens = re.split(r"[,\n;|]+", raw_value)
        aliases: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            cleaned = token.strip()
            if not cleaned:
                continue
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            aliases.append(cleaned)
        return aliases

    def _get_timeclock_close_time(self) -> time:
        value = self._get_config_raw_value(
            "cm_data.timeclock_close_time",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__TIMECLOCK_CLOSE_TIME",
        )
        if not value:
            return time(17, 0)
        cleaned = value.strip()
        if not cleaned:
            return time(17, 0)
        try:
            parts = cleaned.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError) as exc:
            raise UserError("Invalid time for cm_data.timeclock_close_time; expected HH:MM.") from exc
        return time(hour, minute)

    def _get_user_tzinfo(self) -> ZoneInfo:
        tz_name = self.env.user.tz or "UTC"
        try:
            return ZoneInfo(tz_name)
        except Exception:
            _logger.warning("Unknown timezone '%s'; falling back to UTC.", tz_name)
            return ZoneInfo("UTC")

    def _to_local_datetime(self, value: datetime) -> datetime:
        tzinfo = self._get_user_tzinfo()
        return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(tzinfo)

    def _combine_local_date_and_time(self, base_date: date, clock_time: time) -> datetime:
        tzinfo = self._get_user_tzinfo()
        local_dt = datetime.combine(base_date, clock_time, tzinfo=tzinfo)
        return local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    def _close_attendance_missing_checkout(
        self,
        attendance: "odoo.model.hr_attendance",
        *,
        closing_time: time,
        reason: str,
    ) -> None:
        if not attendance.check_in:
            return
        check_in_local = self._to_local_datetime(attendance.check_in)
        close_at = self._combine_local_date_and_time(check_in_local.date(), closing_time)
        if close_at < attendance.check_in:
            close_at = attendance.check_in
        self._close_attendance_with_check_out(
            attendance,
            check_out_time=close_at,
            reason=reason,
        )

    def _close_attendance_with_check_out(
        self,
        attendance: "odoo.model.hr_attendance",
        *,
        check_out_time: datetime,
        reason: str,
    ) -> None:
        if not attendance.check_in:
            return
        attendance_model = self.env["hr.attendance"].sudo()
        adjusted_check_in = attendance.check_in
        previous_attendance = attendance_model.search(
            [
                ("employee_id", "=", attendance.employee_id.id),
                ("check_in", "<=", adjusted_check_in),
                ("id", "!=", attendance.id),
            ],
            order="check_in desc",
            limit=1,
        )
        if previous_attendance and previous_attendance.check_out and previous_attendance.check_out > adjusted_check_in:
            adjusted_check_in = previous_attendance.check_out

        adjusted_check_out = check_out_time
        if adjusted_check_out < adjusted_check_in:
            adjusted_check_out = adjusted_check_in

        next_attendance = attendance_model.search(
            [
                ("employee_id", "=", attendance.employee_id.id),
                ("check_in", ">", adjusted_check_in),
                ("id", "!=", attendance.id),
            ],
            order="check_in asc",
            limit=1,
        )
        if next_attendance and adjusted_check_out > next_attendance.check_in:
            adjusted_check_out = next_attendance.check_in
        if adjusted_check_out < adjusted_check_in:
            adjusted_check_out = adjusted_check_in

        values = {"check_out": adjusted_check_out}
        if adjusted_check_in != attendance.check_in:
            values["check_in"] = adjusted_check_in
        if attendance.check_out == adjusted_check_out and adjusted_check_in == attendance.check_in:
            return
        try:
            attendance.write(values)
        except ValidationError as exc:
            self._log_attendance_fix_failure(
                attendance,
                check_out_time=adjusted_check_out,
                reason=reason,
                error=exc,
            )
            return
        self._log_attendance_fix(attendance, adjusted_check_out, reason)

    def _log_attendance_fix(
        self,
        attendance: "odoo.model.hr_attendance",
        close_at: datetime,
        reason: str,
    ) -> None:
        employee_name = attendance.employee_id.display_name if attendance.employee_id else "Unknown Employee"
        _logger.warning(
            "CM data attendance fix: %s | check_in=%s | check_out=%s | reason=%s",
            employee_name,
            attendance.check_in,
            close_at,
            reason,
        )

    def _log_attendance_fix_failure(
        self,
        attendance: "odoo.model.hr_attendance",
        *,
        check_out_time: datetime,
        reason: str,
        error: Exception,
    ) -> None:
        employee_name = attendance.employee_id.display_name if attendance.employee_id else "Unknown Employee"
        _logger.warning(
            "CM data attendance fix skipped: %s | check_in=%s | check_out=%s | reason=%s | error=%s",
            employee_name,
            attendance.check_in,
            check_out_time,
            reason,
            error,
        )

    def _find_overlapping_attendance(
        self,
        attendance_model: "odoo.model.hr_attendance",
        *,
        employee_id: int,
        check_time: datetime | None,
    ) -> "odoo.model.hr_attendance":
        if not check_time:
            return attendance_model.browse()
        return attendance_model.search(
            [
                ("employee_id", "=", employee_id),
                ("check_in", "<=", check_time),
                "|",
                ("check_out", "=", False),
                ("check_out", ">", check_time),
            ],
            order="check_in desc, id desc",
            limit=1,
        )

    def _log_attendance_overlap(
        self,
        attendance: "odoo.model.hr_attendance",
        *,
        check_time: datetime,
        reason: str,
        updated: bool,
    ) -> None:
        employee_name = attendance.employee_id.display_name if attendance.employee_id else "Unknown Employee"
        _logger.warning(
            "CM data attendance overlap: %s | check_time=%s | attendance_id=%s | updated=%s | reason=%s",
            employee_name,
            check_time,
            attendance.id,
            updated,
            reason,
        )

    def _create_attendance_with_fix(
        self,
        attendance_model: "odoo.model.hr_attendance",
        values: dict[str, object],
        *,
        employee_id: int,
        closing_time: time,
        reason: str,
    ) -> "odoo.model.hr_attendance":
        try:
            return attendance_model.create(values)
        except ValidationError:
            open_attendance_records = attendance_model.search(
                [
                    ("employee_id", "=", employee_id),
                    ("check_out", "=", False),
                ],
                order="check_in desc, id desc",
            )
            if not open_attendance_records:
                raise
            for attendance in open_attendance_records:
                self._close_attendance_missing_checkout(
                    attendance,
                    closing_time=closing_time,
                    reason=reason,
                )
            try:
                return attendance_model.create(values)
            except ValidationError:
                check_time = values.get("check_in") if isinstance(values, dict) else None
                overlapping_attendance = self._find_overlapping_attendance(
                    attendance_model,
                    employee_id=employee_id,
                    check_time=check_time if isinstance(check_time, datetime) else None,
                )
                if overlapping_attendance:
                    updated = False
                    check_out_time = values.get("check_out") if isinstance(values, dict) else None
                    if isinstance(check_out_time, datetime):
                        if not overlapping_attendance.check_out or overlapping_attendance.check_out < check_out_time:
                            overlapping_attendance.write({"check_out": check_out_time})
                            updated = True
                    if isinstance(check_time, datetime):
                        self._log_attendance_overlap(
                            overlapping_attendance,
                            check_time=check_time,
                            reason=reason,
                            updated=updated,
                        )
                    return overlapping_attendance
                raise

    @staticmethod
    def _resolve_punch_time(row: CmDataTimeclockPunch) -> datetime | None:
        return row.check_time or row.created_date or row.time_received or row.edited_day

    @staticmethod
    def _resolve_punch_updated_at(row: CmDataTimeclockPunch) -> datetime | None:
        candidates = [row.edited_day, row.time_received, row.created_date, row.check_time]
        timestamps = [candidate for candidate in candidates if candidate]
        return max(timestamps, default=None)

    @staticmethod
    def _classify_timeclock_check_type(check_type: str | None) -> str | None:
        if not check_type:
            return None
        normalized = check_type.strip().casefold()
        if not normalized:
            return None
        if "out" in normalized:
            return "out"
        if "in" in normalized:
            return "in"
        return None

    @staticmethod
    def _mask_password(password_value: str | None) -> str | None:
        if not password_value:
            return None
        stripped = password_value.strip()
        if not stripped:
            return None
        if len(stripped) <= 4:
            return "****"
        return f"****{stripped[-4:]}"

    @staticmethod
    def _split_employee_name_parts(employee_row: CmDataEmployee) -> tuple[str, str, str]:
        first_name = (employee_row.legal_first or "").strip()
        last_name = (employee_row.legal_last or "").strip()
        nick_name = (employee_row.name or employee_row.legal_first or employee_row.legal_name or "").strip()
        if not first_name and not last_name:
            fallback = (employee_row.legal_name or employee_row.name or "").strip()
            if fallback:
                name_parts = fallback.split()
                first_name = name_parts[0]
                if len(name_parts) > 1:
                    last_name = " ".join(name_parts[1:])
                else:
                    last_name = name_parts[0]
        if not first_name and not last_name:
            first_name = f"Employee {employee_row.record_id}"
        if not nick_name:
            nick_name = first_name or last_name
        return first_name, last_name, nick_name

    @staticmethod
    def _extract_email(value: str | None) -> str | None:
        if not value:
            return None
        candidate = value.strip()
        if not candidate or "@" not in candidate:
            return None
        return candidate

    @staticmethod
    def _as_date(value: datetime | None) -> date | None:
        if not value:
            return None
        return value.date()

    def _commit_and_clear(self) -> None:
        self.env.cr.execute("SET LOCAL synchronous_commit TO OFF")
        self.env.cr.commit()
        self.env.clear()
        self._raise_if_cron_runtime_budget_exhausted(job_name="CM Data Import")

    def _get_commit_interval(self) -> int:
        return self._get_config_int(
            "cm_data.commit_interval",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__COMMIT_INTERVAL",
            default=50,
        )

    def _use_last_sync_at(self) -> bool:
        return self._get_config_bool(
            "cm_data.use_last_sync_at",
            "ENV_OVERRIDE_CONFIG_PARAM__CM_DATA__USE_LAST_SYNC_AT",
            default=True,
        )

    def _maybe_commit(self, processed_count: int, commit_interval: int, *, label: str) -> bool:
        if commit_interval <= 0:
            return False
        if processed_count % commit_interval != 0:
            return False
        self._commit_and_clear()
        _logger.info("CM data import: committed %s %s records", processed_count, label)
        return True

    def _get_external_id_record(
        self,
        system: "odoo.model.external_system",
        external_id_value: str,
        resource: str,
    ) -> "odoo.model.external_id":
        return (
            self.env["external.id"]
            .sudo()
            .search(
                [
                    ("system_id", "=", system.id),
                    ("resource", "=", resource),
                    ("external_id", "=", external_id_value),
                ],
                limit=1,
            )
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

    def _get_or_create_by_external_id_with_sync(
        self,
        record_model: "odoo.model.external_id_mixin",
        system: "odoo.model.external_system",
        external_id_value: str,
        values: dict[str, object],
        *,
        resource: str,
        updated_at: datetime | None,
        sync_started_at: datetime,
    ) -> "odoo.model.external_id_mixin":
        if updated_at and not self._should_process_external_row(system, external_id_value, resource, updated_at):
            existing_record = record_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                resource,
            )
            if existing_record:
                return existing_record
        record = record_model.get_or_create_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            external_id_value,
            values,
            resource=resource,
        )
        sync_timestamp = updated_at or sync_started_at
        self._mark_external_id_synced(system, external_id_value, resource, sync_timestamp)
        return record

    def _get_cm_data_system(self) -> "odoo.model.external_system":
        desired_id_format = r"^[A-Za-z0-9._-]+$"
        system = self.env["external.system"].ensure_system(
            code=EXTERNAL_SYSTEM_CODE,
            name="CM Data",
            id_format=desired_id_format,
            sequence=80,
            active=True,
            applicable_model_xml_ids=EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
        )
        if system.id_format != desired_id_format:
            system.sudo().write({"id_format": desired_id_format})
        return system

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
