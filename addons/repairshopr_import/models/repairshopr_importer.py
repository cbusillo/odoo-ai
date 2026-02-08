import logging
import os
import re
from datetime import datetime, timedelta

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
REPAIRSHOPR_TRANSACTION_CUTOFF = datetime(2022, 1, 1)

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
BID_PATTERN = re.compile(
    r"\bBID\s*(?:NO|NUMBER|#)?\s*[:#\-]?\s*(?P<bid>[A-Z0-9][A-Z0-9\- ]{1,30})\b",
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
    "cm_skip_required_fields": True,
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
        transaction_start_datetime = self._apply_transaction_cutoff(start_datetime)
        repairshopr_client = self._build_client()
        try:
            system = self._get_repairshopr_system()
            self._import_customers(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_products(repairshopr_client, start_datetime, system, sync_started_at)
            self._import_tickets(repairshopr_client, transaction_start_datetime, system, sync_started_at)
            self._import_estimates(repairshopr_client, transaction_start_datetime, system, sync_started_at)
            self._import_invoices(repairshopr_client, transaction_start_datetime, system, sync_started_at)
            self._backfill_transport_order_devices()
        except Exception as exc:
            _logger.exception("RepairShopr import failed")
            self._record_last_run("failed", str(exc))
            raise
        finally:
            repairshopr_client.clear_cache()

        self._record_last_run("success", "")
        if update_last_sync and use_last_sync_at:
            self._set_last_sync_at(sync_started_at)

    @staticmethod
    def _apply_transaction_cutoff(start_datetime: datetime | None) -> datetime:
        if start_datetime and start_datetime > REPAIRSHOPR_TRANSACTION_CUTOFF:
            return start_datetime
        return REPAIRSHOPR_TRANSACTION_CUTOFF

    @staticmethod
    def _is_before_transaction_cutoff(timestamp: datetime | None) -> bool:
        if not timestamp:
            return False
        return timestamp < REPAIRSHOPR_TRANSACTION_CUTOFF

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

    def _backfill_transport_order_devices(self) -> None:
        if "service.transport.order" not in self.env:
            _logger.info("Transport device backfill skipped; service.transport.order not installed.")
            return
        if "service.intake.order" not in self.env or "service.intake.order.device" not in self.env:
            _logger.info("Transport device backfill skipped; intake models not installed.")
            return
        if "service.transport.order.device" not in self.env:
            _logger.info("Transport device backfill skipped; transport device model missing.")
            return
        if "external.id" not in self.env or "external.system" not in self.env:
            _logger.info("Transport device backfill skipped; external ID models not installed.")
            return
        if "identifier.index" not in self.env:
            _logger.info("Transport device backfill skipped; identifier index not installed.")
            return

        transport_order_model = self.env["service.transport.order"].sudo().with_context(IMPORT_CONTEXT)
        intake_order_model = self.env["service.intake.order"].sudo().with_context(IMPORT_CONTEXT)
        intake_device_model = self.env["service.intake.order.device"].sudo().with_context(IMPORT_CONTEXT)
        transport_device_model = self.env["service.transport.order.device"].sudo().with_context(IMPORT_CONTEXT)
        ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)

        cm_system = self._get_external_system_by_code("cm_data")
        if not cm_system:
            _logger.info("Transport device backfill skipped; CM data external system not found.")
            return
        transport_order_ids = self._get_external_ids_for_model(
            cm_system.id,
            "delivery_log",
            "service.transport.order",
        )
        if not transport_order_ids:
            _logger.info("Transport device backfill skipped; no imported transport orders found.")
            return
        transport_orders = transport_order_model.browse(transport_order_ids).exists().sorted(
            key=lambda record: (record.arrival_date or record.scheduled_date or record.create_date, record.id)
        )
        if not transport_orders:
            _logger.info("Transport device backfill skipped; no transport orders found.")
            return

        repairshopr_system = self._get_external_system_by_code(EXTERNAL_SYSTEM_CODE)
        if not repairshopr_system:
            _logger.info("Transport device backfill skipped; RepairShopr system not found.")
            return
        imported_ticket_ids = self._get_external_ids_for_model(
            repairshopr_system.id,
            RESOURCE_TICKET,
            "helpdesk.ticket",
        )
        if not imported_ticket_ids:
            _logger.info("Transport device backfill skipped; no imported tickets found.")
            return
        ticket_records = ticket_model.browse(imported_ticket_ids).exists()
        ticket_records = ticket_records.filtered(lambda record: record.intake_order_id)
        if not ticket_records:
            _logger.info("Transport device backfill skipped; no intake orders linked to imported tickets.")
            return

        intake_orders = ticket_records.mapped("intake_order_id").filtered(
            lambda order: not order.transport_order
        )
        if not intake_orders:
            _logger.info("Transport device backfill skipped; no intake orders need transport links.")
            return

        device_counts: dict[int, int] = {}
        grouped_counts = transport_device_model.read_group(
            [("transport_order", "in", transport_order_ids)],
            ["transport_order"],
            ["transport_order"],
        )
        for group in grouped_counts:
            transport_id = group.get("transport_order")[0] if group.get("transport_order") else None
            if transport_id:
                device_counts[transport_id] = int(group.get("transport_order_count", 0) or 0)

        alias_map = self._build_cm_location_alias_map(cm_system)

        transport_order_info: list[dict[str, object]] = []
        orders_by_partner: dict[int, list[dict[str, object]]] = {}
        for transport_order in transport_orders:
            partner_id = transport_order.client.id if transport_order.client else None
            if not partner_id:
                continue
            order_date = self._resolve_transport_order_date(transport_order)
            location_key = self._normalize_location_key(transport_order.cm_data_location_name)
            location_option_id = alias_map.get(location_key)
            capacity = int(transport_order.cm_data_units or transport_order.quantity_in_counted or 0)
            used_count = device_counts.get(transport_order.id, 0)
            note_identifiers = self._extract_transport_order_identifiers(transport_order)
            note_device_ids = self._resolve_devices_from_identifiers(
                note_identifiers,
                partner_id=partner_id,
            )
            info: dict[str, object] = {
                "id": transport_order.id,
                "partner_id": partner_id,
                "date": order_date,
                "location_key": location_key,
                "location_option_id": location_option_id,
                "capacity": capacity,
                "used": used_count,
                "note_device_ids": note_device_ids,
            }
            transport_order_info.append(info)
            orders_by_partner.setdefault(partner_id, []).append(info)

        intake_order_ids = self._get_intake_orders_with_devices(intake_device_model, intake_orders.ids)
        if not intake_order_ids:
            _logger.info("Transport device backfill skipped; no intake devices found.")
            return

        intake_orders = intake_orders.filtered(lambda order: order.id in set(intake_order_ids))
        intake_orders = intake_orders.sorted(key=lambda record: (record.finish_date or record.id, record.id))

        intake_info_by_id: dict[int, dict[str, object]] = {}
        for intake_order in intake_orders:
            partner_id = intake_order.client.id if intake_order.client else None
            if not partner_id:
                continue
            intake_info_by_id[intake_order.id] = {
                "id": intake_order.id,
                "client_id": partner_id,
                "finish_date": intake_order.finish_date,
            }

        tickets_by_intake_id = self._build_ticket_location_map(ticket_records)
        devices_by_intake_id = self._build_intake_device_map(intake_device_model, list(intake_info_by_id))
        for intake_id, device_ids in devices_by_intake_id.items():
            if intake_id in intake_info_by_id:
                intake_info_by_id[intake_id]["device_ids"] = device_ids

        commit_interval = self._get_commit_interval()
        processed_count = 0
        linked_intake_orders = 0
        created_devices = 0
        linked_tickets = 0
        skipped_missing_match = 0

        for intake_id, intake_info in intake_info_by_id.items():
            device_ids = devices_by_intake_id.get(intake_id, [])
            if not device_ids:
                continue
            partner_id = intake_info.get("client_id")
            if not partner_id:
                continue
            candidate_orders = orders_by_partner.get(partner_id, [])
            if not candidate_orders:
                skipped_missing_match += 1
                continue

            ticket_info = tickets_by_intake_id.get(intake_id)
            selected_order = self._select_transport_order_for_intake(
                intake_info,
                ticket_info,
                candidate_orders,
                device_ids,
            )
            if not selected_order:
                skipped_missing_match += 1
                continue

            created_count, ticket_linked = self._link_intake_to_transport_order(
                intake_id,
                device_ids,
                selected_order,
                ticket_info,
                transport_device_model,
                intake_order_model,
                ticket_model,
            )
            if created_count > 0:
                created_devices += created_count
                used_count = int(selected_order.get("used", 0))
                selected_order["used"] = used_count + created_count
            if ticket_linked:
                linked_tickets += 1
            linked_intake_orders += 1
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="transport device"):
                transport_device_model = self.env["service.transport.order.device"].sudo().with_context(IMPORT_CONTEXT)
                intake_order_model = self.env["service.intake.order"].sudo().with_context(IMPORT_CONTEXT)
                ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)

        _logger.info(
            "Transport device backfill: linked %s intake orders, created %s device lines, linked %s tickets, skipped %s",
            linked_intake_orders,
            created_devices,
            linked_tickets,
            skipped_missing_match,
        )

        note_device_created = self._create_transport_devices_from_notes(
            transport_device_model,
            transport_order_info,
        )
        if note_device_created:
            _logger.info("Transport device backfill: created %s note-derived device lines", note_device_created)

    @staticmethod
    def _normalize_location_key(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().lower().split())

    @staticmethod
    def _resolve_transport_order_date(transport_order: "odoo.model.service_transport_order") -> datetime | None:
        return transport_order.arrival_date or transport_order.scheduled_date or transport_order.create_date

    def _build_cm_location_alias_map(self, cm_system: "odoo.model.external_system") -> dict[str, int]:
        if "school.location.option.alias" not in self.env:
            return {}
        alias_model = self.env["school.location.option.alias"].sudo()
        alias_map: dict[str, int] = {}
        for alias in alias_model.search([("system_id", "=", cm_system.id)]):
            normalized = self._normalize_location_key(alias.external_key)
            if normalized and alias.location_option_id:
                alias_map[normalized] = alias.location_option_id.id
        return alias_map

    @staticmethod
    def _get_intake_orders_with_devices(
        intake_device_model: "odoo.model.service_intake_order_device",
        intake_order_ids: list[int],
    ) -> list[int]:
        if not intake_order_ids:
            return []
        grouped = intake_device_model.read_group(
            [("intake_order", "in", intake_order_ids)],
            ["intake_order"],
            ["intake_order"],
        )
        intake_ids: list[int] = []
        for group in grouped:
            intake_id = group.get("intake_order")[0] if group.get("intake_order") else None
            if intake_id:
                intake_ids.append(intake_id)
        return intake_ids

    def _build_ticket_location_map(
        self,
        tickets: "odoo.model.helpdesk_ticket",
    ) -> dict[int, dict[str, object]]:
        if not tickets:
            return {}
        ticket_info_map: dict[int, dict[str, object]] = {}
        for ticket in tickets:
            intake_order = ticket.intake_order_id
            if not intake_order:
                continue
            location_option_ids: list[int] = []
            location_keys: list[str] = []
            for option_field in [
                "transport_location_option_id",
                "transport_location_2_option_id",
                "location_option_id",
            ]:
                if option_field in ticket._fields:
                    option_record = ticket[option_field]
                    if option_record:
                        location_option_ids.append(option_record.id)
                        name_key = self._normalize_location_key(option_record.name)
                        if name_key and name_key not in location_keys:
                            location_keys.append(name_key)
            for label_field in [
                "transport_location_label",
                "transport_location_2_label",
                "location_label",
                "location_raw",
            ]:
                if label_field in ticket._fields:
                    label_value = ticket[label_field]
                    normalized = self._normalize_location_key(label_value)
                    if normalized and normalized not in location_keys:
                        location_keys.append(normalized)
            ticket_info_map[intake_order.id] = {
                "ticket_id": ticket.id,
                "partner_id": ticket.partner_id.id if ticket.partner_id else None,
                "location_option_ids": location_option_ids,
                "location_keys": location_keys,
            }
        return ticket_info_map

    @staticmethod
    def _build_intake_device_map(
        intake_device_model: "odoo.model.service_intake_order_device",
        intake_order_ids: list[int],
    ) -> dict[int, list[int]]:
        if not intake_order_ids:
            return {}
        devices_by_intake: dict[int, list[int]] = {}
        intake_devices = intake_device_model.search([("intake_order", "in", intake_order_ids)])
        for intake_device in intake_devices:
            intake_order = intake_device.intake_order
            if not intake_order or not intake_device.device:
                continue
            device_ids = devices_by_intake.setdefault(intake_order.id, [])
            device_ids.append(intake_device.device.id)
        return devices_by_intake

    def _select_transport_order_for_intake(
        self,
        intake_info: dict[str, object],
        ticket_info: dict[str, object] | None,
        candidate_orders: list[dict[str, object]],
        device_ids: list[int],
    ) -> dict[str, object] | None:
        finish_date = intake_info.get("finish_date")
        if not finish_date:
            return None

        def matches_location(order_info: dict[str, object]) -> bool:
            if not ticket_info:
                return False
            ticket_option_ids = ticket_info.get("location_option_ids") or []
            order_option_id = order_info.get("location_option_id")
            if order_option_id and ticket_option_ids and order_option_id in ticket_option_ids:
                return True
            order_location_key = order_info.get("location_key")
            if order_location_key:
                ticket_keys = ticket_info.get("location_keys") or []
                return order_location_key in ticket_keys
            return False

        def is_within_window(order_info: dict[str, object], window_days: int) -> bool:
            order_date = order_info.get("date")
            if not order_date:
                return False
            window = timedelta(days=window_days)
            return abs(order_date - finish_date) <= window

        for window_days in (2, 7):
            window_candidates = [
                order_info
                for order_info in candidate_orders
                if is_within_window(order_info, window_days)
            ]
            if not window_candidates:
                continue
            if ticket_info:
                location_candidates = [
                    order_info for order_info in window_candidates if matches_location(order_info)
                ]
                if location_candidates:
                    window_candidates = location_candidates
            device_candidates = self._filter_orders_by_device_ids(window_candidates, device_ids)
            if device_candidates:
                window_candidates = device_candidates
            return self._pick_best_transport_order(window_candidates, finish_date)
        return None

    @staticmethod
    def _filter_orders_by_device_ids(
        candidates: list[dict[str, object]],
        device_ids: list[int],
    ) -> list[dict[str, object]]:
        if not device_ids:
            return []
        device_id_set = set(device_ids)
        return [
            order_info
            for order_info in candidates
            if device_id_set.intersection(order_info.get("note_device_ids") or set())
        ]

    def _get_external_system_by_code(self, code: str) -> "odoo.model.external_system | None":
        system_model = self.env["external.system"].sudo()
        system = system_model.search([("code", "=", code)], limit=1)
        return system if system else None

    def _get_external_ids_for_model(
        self,
        system_id: int,
        resource: str,
        model_name: str,
    ) -> list[int]:
        external_id_model = self.env["external.id"].sudo().with_context(active_test=False)
        records = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("res_model", "=", model_name),
            ]
        )
        return [record.res_id for record in records if record.res_id]

    def _extract_transport_order_identifiers(
        self,
        transport_order: "odoo.model.service_transport_order",
    ) -> dict[str, set[str]]:
        notes = [
            transport_order.cm_data_notes,
            transport_order.cm_data_edit_notes,
            transport_order.cm_data_ocr_notes,
        ]
        identifiers: dict[str, set[str]] = {}
        for note in notes:
            if not note:
                continue
            extracted = self._extract_identifiers_from_text(note)
            for identifier_type, identifier_values in extracted.items():
                identifiers.setdefault(identifier_type, set()).update(identifier_values)
        return identifiers

    def _extract_identifiers_from_text(self, text: str) -> dict[str, set[str]]:
        identifiers: dict[str, set[str]] = {}
        for pattern, group_name, identifier_type in (
            (SERIAL_PATTERN, "serial", "serial"),
            (ASSET_TAG_PATTERN, "tag", "asset_tag"),
            (IMEI_PATTERN, "imei", "imei"),
        ):
            matches = [match.group(group_name) for match in pattern.finditer(text)]
            cleaned_values = {value.strip() for value in matches if value and value.strip()}
            if cleaned_values:
                identifiers[identifier_type] = cleaned_values
        return identifiers

    def _resolve_devices_from_identifiers(
        self,
        identifiers: dict[str, set[str]],
        *,
        partner_id: int | None,
    ) -> set[int]:
        if not identifiers:
            return set()
        identifier_model = self.env["identifier.index"].sudo().with_context(active_test=False)
        device_model = self.env["service.device"].sudo().with_context(active_test=False)
        resolved_ids: set[int] = set()

        for identifier_type, identifier_values in identifiers.items():
            for identifier_value in identifier_values:
                normalized_value = self._normalize_identifier_value(identifier_value)
                if not normalized_value:
                    continue
                preferred_ids: set[int] = set()
                index_matches = identifier_model.search(
                    [
                        ("identifier_type", "=", identifier_type),
                        ("identifier_normalized", "=", normalized_value),
                        ("res_model", "=", "service.device"),
                    ]
                )
                for index_match in index_matches:
                    device_record = device_model.browse(index_match.res_id)
                    if not device_record.exists():
                        continue
                    if partner_id and device_record.owner and device_record.owner.id != partner_id:
                        continue
                    preferred_ids.add(device_record.id)

                if not preferred_ids:
                    search_domain = self._build_device_search_domain(identifier_value)
                    if partner_id:
                        owner_domain = ["&", ("owner", "=", partner_id)]
                        search_domain = owner_domain + search_domain
                    matches = device_model.search(search_domain, limit=5)
                    if not matches and partner_id:
                        matches = device_model.search(self._build_device_search_domain(identifier_value), limit=5)
                    if matches:
                        preferred_ids.update(matches.ids)

                if preferred_ids:
                    resolved_ids.update(preferred_ids)

        return resolved_ids

    @staticmethod
    def _build_device_search_domain(identifier_value: str) -> list[object]:
        value = identifier_value.strip()
        return [
            "|",
            "|",
            "|",
            ("serial_number", "ilike", value),
            ("asset_tag", "ilike", value),
            ("asset_tag_secondary", "ilike", value),
            ("imei", "ilike", value),
        ]

    def _create_transport_devices_from_notes(
        self,
        transport_device_model: "odoo.model.service_transport_order.device",
        transport_order_info: list[dict[str, object]],
    ) -> int:
        if not transport_order_info:
            return 0
        created_count = 0
        commit_interval = self._get_commit_interval()
        processed_count = 0
        for order_info in transport_order_info:
            transport_order_id = int(order_info.get("id") or 0)
            if not transport_order_id:
                continue
            note_device_ids = set(order_info.get("note_device_ids") or set())
            if not note_device_ids:
                continue
            existing_lines = transport_device_model.search(
                [
                    ("transport_order", "=", transport_order_id),
                    ("device", "in", list(note_device_ids)),
                ]
            )
            existing_device_ids = set(existing_lines.mapped("device").ids)
            create_values = [
                {
                    "transport_order": transport_order_id,
                    "device": device_id,
                    "movement_type": "in",
                }
                for device_id in note_device_ids
                if device_id not in existing_device_ids
            ]
            if create_values:
                transport_device_model.create(create_values)
                created_count += len(create_values)
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="transport note device"):
                transport_device_model = self.env["service.transport.order.device"].sudo().with_context(IMPORT_CONTEXT)
        return created_count

    @staticmethod
    def _pick_best_transport_order(
        candidates: list[dict[str, object]],
        finish_date: datetime,
    ) -> dict[str, object] | None:
        if not candidates:
            return None

        def sort_key(order_info: dict[str, object]) -> tuple[bool, timedelta, datetime, int]:
            order_date = order_info.get("date") or finish_date
            capacity = int(order_info.get("capacity", 0) or 0)
            used = int(order_info.get("used", 0) or 0)
            is_full = capacity > 0 and used >= capacity
            return (
                is_full,
                abs(order_date - finish_date),
                order_date,
                int(order_info.get("id", 0) or 0),
            )

        candidates.sort(key=sort_key)
        return candidates[0]

    def _link_intake_to_transport_order(
        self,
        intake_id: int,
        device_ids: list[int],
        order_info: dict[str, object],
        ticket_info: dict[str, object] | None,
        transport_device_model: "odoo.model.service_transport_order_device",
        intake_order_model: "odoo.model.service_intake_order",
        ticket_model: "odoo.model.helpdesk_ticket",
    ) -> tuple[int, bool]:
        transport_order_id = int(order_info.get("id") or 0)
        if not transport_order_id:
            return 0, False
        unique_device_ids = list({device_id for device_id in device_ids if device_id})
        if not unique_device_ids:
            return 0, False
        existing_lines = transport_device_model.search(
            [
                ("transport_order", "=", transport_order_id),
                ("device", "in", unique_device_ids),
            ]
        )
        existing_device_ids = set(existing_lines.mapped("device").ids)
        create_values = [
            {
                "transport_order": transport_order_id,
                "device": device_id,
                "movement_type": "in",
            }
            for device_id in unique_device_ids
            if device_id not in existing_device_ids
        ]
        if create_values:
            transport_device_model.create(create_values)
        intake_order_model.browse(intake_id).write({"transport_order": transport_order_id})
        ticket_linked = False
        if ticket_info:
            ticket_id = int(ticket_info.get("ticket_id") or 0)
            if ticket_id:
                ticket_record = ticket_model.browse(ticket_id)
                if not ticket_record.transport_order_id:
                    ticket_record.write({"transport_order_id": transport_order_id})
                    ticket_linked = True
        return len(create_values), ticket_linked

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
        for match in BID_PATTERN.finditer(text):
            bid_value = match.group("bid").strip()
            if bid_value:
                identifiers["bid"].add(bid_value)
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
        other_value = getattr(properties, "other", None)
        if other_value:
            for match in BID_PATTERN.finditer(str(other_value)):
                bid_value = match.group("bid").strip()
                if bid_value:
                    identifiers["bid"].add(bid_value)
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
