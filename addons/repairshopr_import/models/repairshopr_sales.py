import csv
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg2 import IntegrityError

from odoo import fields, models
from odoo.exceptions import UserError

from ..services import repairshopr_sync_models as repairshopr_models
from ..services.repairshopr_sync_client import RepairshoprSyncClient

from .repairshopr_importer import (
    ASSET_TAG_PATTERN,
    CLAIM_PATTERN,
    EXTERNAL_SYSTEM_CODE,
    IMPORT_CONTEXT,
    IMEI_PATTERN,
    PO_PATTERN,
    RESOURCE_ESTIMATE,
    RESOURCE_INVOICE,
    RESOURCE_TICKET,
    SERIAL_PATTERN,
)

_logger = logging.getLogger(__name__)


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    _TICKET_LINK_IDENTIFIER_TYPES = (
        "serial",
        "asset_tag",
        "asset_tag_secondary",
        "claim",
        "ticket",
    )

    @staticmethod
    def _split_lines(value: object) -> list[str]:
        if not value:
            return []
        text = str(value).replace("\r", "\n")
        return [line.strip() for line in text.split("\n") if line.strip()]

    @classmethod
    def _is_needs_estimate_marker(cls, text: str) -> bool:
        normalized = " ".join(text.strip().lower().split())
        return "needs estimate" in normalized

    @classmethod
    def _is_device_line(cls, text: str) -> bool:
        normalized = " ".join(text.strip().lower().split())
        if not normalized:
            return False
        non_device_prefixes = (
            "summary",
            "level 1 tech support",
            "diagnostic fee per unit",
            "district reference",
            "quote #",
            "invoice #",
            "district invoices",
            "remote support provided",
            "capped pricing discount",
        )
        if normalized.startswith(non_device_prefixes):
            return False
        if "needs estimate" in normalized:
            return False
        if SERIAL_PATTERN.search(text) or ASSET_TAG_PATTERN.search(text) or CLAIM_PATTERN.search(text) or PO_PATTERN.search(text):
            return True
        if "replacement" in normalized or "repair" in normalized:
            return True
        if " - " in text:
            left_side = text.split(" - ", 1)[0].strip()
            if re.search(r"[A-Za-z]", left_side) and re.search(r"\d", left_side):
                return True
        if re.search(r"\(\s*(?:n/c|\$)", normalized):
            return True
        if re.search(r"\$\s*\d", normalized):
            return True
        return False

    @staticmethod
    def _is_summary_line(text: str) -> bool:
        normalized = " ".join(text.strip().lower().split())
        return normalized.startswith("summary")

    @staticmethod
    def _clean_summary_line(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""
        match = re.match(r"(?i)^summary\s*[:\-]\s*(?P<summary>.+)$", cleaned)
        if match:
            return match.group("summary").strip()
        if cleaned.lower().startswith("summary"):
            return cleaned[len("summary") :].lstrip(" :\t-")
        return cleaned

    @classmethod
    def _extract_device_identifiers_from_line(cls, text: str) -> dict[str, str]:
        identifiers: dict[str, str] = {}
        for match in SERIAL_PATTERN.finditer(text):
            cleaned = cls._clean_identifier_value(match.group("serial"), identifier_type="serial")
            if cleaned:
                identifiers.setdefault("serial", cleaned)
        for match in ASSET_TAG_PATTERN.finditer(text):
            cleaned = cls._clean_identifier_value(match.group("tag"), identifier_type="asset_tag")
            if cleaned:
                identifiers.setdefault("asset_tag", cleaned)
        for match in IMEI_PATTERN.finditer(text):
            cleaned = cls._clean_identifier_value(match.group("imei"), identifier_type="imei")
            if cleaned:
                identifiers.setdefault("imei", cleaned)
        for match in CLAIM_PATTERN.finditer(text):
            cleaned = cls._clean_identifier_value(match.group("claim"), identifier_type="claim")
            if cleaned:
                identifiers.setdefault("claim", cleaned)
        for match in PO_PATTERN.finditer(text):
            cleaned = cls._clean_identifier_value(match.group("po"), identifier_type="po")
            if cleaned:
                identifiers.setdefault("po", cleaned)
        return identifiers

    @staticmethod
    def _clean_identifier_value(value: str | None, *, identifier_type: str) -> str | None:
        if not value:
            return None
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            return None
        normalized = cleaned.lower()
        if normalized in {"n/a", "na", "none", "unknown", "unk", "tbd", "null", "-"}:
            return None
        if identifier_type == "imei":
            digits = "".join(ch for ch in cleaned if ch.isdigit())
            return digits if len(digits) >= 8 else None
        if identifier_type in {"serial", "asset_tag"}:
            if len(cleaned) < 4:
                return None
            if not any(ch.isdigit() for ch in cleaned):
                return None
        return cleaned

    @classmethod
    def _extract_identifiers_from_comments(
        cls,
        comments: list[repairshopr_models.TicketComment],
    ) -> dict[str, set[str]]:
        identifiers: dict[str, set[str]] = {}
        for comment in comments or []:
            for text in (comment.subject, comment.body):
                for line in cls._split_lines(text or ""):
                    extracted = cls._extract_device_identifiers_from_line(line)
                    for key, value in extracted.items():
                        identifiers.setdefault(key, set()).add(value)
        return identifiers

    @staticmethod
    def _merge_comment_identifiers(
        target: dict[str, object],
        comment_identifiers: dict[str, set[str]],
    ) -> None:
        for key in ("serial", "asset_tag", "imei"):
            if target.get(key):
                continue
            values = comment_identifiers.get(key) or set()
            if len(values) == 1:
                target[key] = next(iter(values))

    @staticmethod
    def _build_placeholder_serial(
        ticket: repairshopr_models.Ticket,
        partner: "odoo.model.res_partner",
        model_label: str | None,
        *,
        ordinal: int,
    ) -> str:
        ticket_ref = ticket.number or ticket.id
        model_token = (model_label or "unknown").strip().replace(" ", "-")
        serial = f"UNIDENTIFIED-{partner.id}-{ticket_ref}-{ordinal}-{model_token}"
        return serial[:64]

    @classmethod
    def _extract_model_from_line(cls, text: str) -> str | None:
        if not cls._is_device_line(text):
            return None
        if " - " in text:
            return text.split(" - ", 1)[0].strip() or None
        if "-" in text:
            return text.split("-", 1)[0].strip() or None
        return None

    @staticmethod
    def _merge_identifiers_into_pending(
        pending_device: dict[str, object],
        identifiers: dict[str, str],
    ) -> bool:
        identifier_map = {
            "serial": "serial",
            "asset_tag": "asset_tag",
            "imei": "imei",
            "claim": "claim_number",
            "po": "po_number",
        }
        for identifier_key, pending_key in identifier_map.items():
            incoming_value = identifiers.get(identifier_key)
            if not incoming_value:
                continue
            existing_value = pending_device.get(pending_key)
            if existing_value and str(existing_value).strip() != incoming_value:
                return False
        for identifier_key, pending_key in identifier_map.items():
            incoming_value = identifiers.get(identifier_key)
            if not incoming_value:
                continue
            if not pending_device.get(pending_key):
                pending_device[pending_key] = incoming_value
        return True

    @staticmethod
    def _resolve_case_indicator(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower()
        if normalized in {"yes", "y", "true"}:
            return "yes"
        if normalized in {"no", "n", "false"}:
            return "no"
        return None

    def _find_or_create_device(
        self,
        *,
        partner: "odoo.model.res_partner",
        model_label: str | None,
        serial_number: str | None,
        asset_tag: str | None,
        asset_tag_secondary: str | None,
        imei: str | None,
        is_placeholder: bool = False,
    ) -> "odoo.model.service_device":
        device_model = self.env["service.device"].sudo().with_context(IMPORT_CONTEXT)
        model_model = self.env["service.device.model"].sudo().with_context(IMPORT_CONTEXT)
        device_record = None
        if serial_number:
            device_record = device_model.search([("serial_number", "=", serial_number)], limit=1)
        if not device_record and asset_tag:
            asset_domain = [("asset_tag", "=", asset_tag)]
            if partner:
                asset_domain.append(("owner", "=", partner.id))
            device_record = device_model.search(asset_domain, limit=1)
        if not device_record and asset_tag_secondary:
            asset_secondary_domain = [("asset_tag_secondary", "=", asset_tag_secondary)]
            if partner:
                asset_secondary_domain.append(("owner", "=", partner.id))
            device_record = device_model.search(asset_secondary_domain, limit=1)
        if not device_record and imei:
            device_record = device_model.search([("imei", "=", imei)], limit=1)

        device_model_record = None
        if model_label:
            device_model_record = model_model.search([("number", "=", model_label)], limit=1)
        if not device_model_record:
            device_model_record = model_model.search([], limit=1)
        if not device_model_record:
            device_model_record = model_model.create({"number": model_label or "Unknown"})

        if device_record:
            update_values: dict[str, object] = {}
            if not device_record.model:
                update_values["model"] = device_model_record.id
            if not device_record.owner:
                update_values["owner"] = partner.id
            if asset_tag and not device_record.asset_tag:
                update_values["asset_tag"] = asset_tag
            if asset_tag_secondary and not device_record.asset_tag_secondary:
                update_values["asset_tag_secondary"] = asset_tag_secondary
            if imei and not device_record.imei:
                update_values["imei"] = imei
            if is_placeholder and not device_record.is_serial_unavailable:
                update_values["is_serial_unavailable"] = True
            if update_values:
                device_record.write(update_values)
            return device_record

        return device_model.create(
            {
                "serial_number": serial_number,
                "asset_tag": asset_tag,
                "asset_tag_secondary": asset_tag_secondary,
                "imei": imei,
                "model": device_model_record.id,
                "owner": partner.id,
                "is_serial_unavailable": is_placeholder or not any(
                    [serial_number, asset_tag, asset_tag_secondary, imei]
                ),
            }
        )

    def _build_intake_from_line_items(
        self,
        ticket: repairshopr_models.Ticket,
        partner: "odoo.model.res_partner",
        *,
        line_items: list[dict[str, Any]],
    ) -> tuple["odoo.model.service_intake_order | None", list["odoo.model.service_intake_order_device"]]:
        if not line_items:
            return None, []
        device_lines: list[dict[str, object]] = []
        pending_device: dict[str, object] | None = None
        needs_estimate_next = False
        needs_estimate_all = False
        comment_identifiers = self._extract_identifiers_from_comments(ticket.comments)

        def flush_pending() -> None:
            nonlocal pending_device
            if not pending_device:
                return
            device_lines.append(pending_device)
            pending_device = None

        for line_item in line_items:
            line_text = line_item.get("name") or line_item.get("item") or ""
            lines = self._split_lines(line_text)
            if not lines:
                continue
            for line in lines:
                if self._is_needs_estimate_marker(line):
                    if pending_device is None and not device_lines:
                        needs_estimate_all = True
                    else:
                        needs_estimate_next = True
                    continue
                if self._is_summary_line(line):
                    if pending_device is not None:
                        summary_notes = pending_device.setdefault("summary_notes", [])
                        if isinstance(summary_notes, list):
                            cleaned_summary = self._clean_summary_line(line)
                            if cleaned_summary:
                                summary_notes.append(cleaned_summary)
                    continue
                model_label = self._extract_model_from_line(line)
                identifiers = self._extract_device_identifiers_from_line(line)
                if identifiers and pending_device is not None and not model_label:
                    if self._merge_identifiers_into_pending(pending_device, identifiers):
                        continue
                if model_label or identifiers:
                    flush_pending()
                    pending_device = {
                        "model_label": model_label,
                        "serial": identifiers.get("serial"),
                        "asset_tag": identifiers.get("asset_tag"),
                        "imei": identifiers.get("imei"),
                        "claim_number": identifiers.get("claim"),
                        "po_number": identifiers.get("po"),
                        "customer_notes": [],
                        "summary_notes": [],
                        "needs_estimate": needs_estimate_all or needs_estimate_next,
                    }
                    if comment_identifiers:
                        self._merge_comment_identifiers(pending_device, comment_identifiers)
                    needs_estimate_next = False
                    continue
                if pending_device is not None:
                    customer_notes = pending_device.setdefault("customer_notes", [])
                    if isinstance(customer_notes, list):
                        customer_notes.append(line)
        flush_pending()

        if not device_lines:
            return None, []

        intake_model = self.env["service.intake.order"].sudo().with_context(IMPORT_CONTEXT)
        intake_device_model = self.env["service.intake.order.device"].sudo().with_context(IMPORT_CONTEXT)

        intake_order = intake_model.create(
            {
                "client": partner.id,
                "state": "finished",
                "finish_date": ticket.created_at,
            }
        )

        created_lines: list["odoo.model.service_intake_order_device"] = []
        quality_control_candidates: dict[int, dict[str, object]] = {}
        placeholder_ordinal = 0
        for device_line in device_lines:
            model_label = device_line.get("model_label")
            if model_label is not None:
                model_label = str(model_label)
            serial_number = device_line.get("serial") or (
                (ticket.properties.s_n_num or ticket.properties.s_n) if ticket.properties else None
            )
            if serial_number is not None:
                serial_number = str(serial_number)
            asset_tag = device_line.get("asset_tag") or (ticket.properties.tag_num if ticket.properties else None)
            if asset_tag is not None:
                asset_tag = str(asset_tag)
            asset_tag_secondary = ticket.properties.tag_num_2 if ticket.properties else None
            if asset_tag_secondary is not None:
                asset_tag_secondary = str(asset_tag_secondary)
            imei = device_line.get("imei")
            if imei is not None:
                imei = str(imei)
            is_placeholder = False
            if not any([serial_number, asset_tag, asset_tag_secondary, imei]):
                placeholder_ordinal += 1
                serial_number = self._build_placeholder_serial(
                    ticket,
                    partner,
                    model_label,
                    ordinal=placeholder_ordinal,
                )
                is_placeholder = True
            device_record = self._find_or_create_device(
                partner=partner,
                model_label=model_label,
                serial_number=serial_number,
                asset_tag=asset_tag,
                asset_tag_secondary=asset_tag_secondary,
                imei=imei,
                is_placeholder=is_placeholder,
            )
            customer_notes = device_line.get("customer_notes")
            notes = "\n".join(customer_notes) if isinstance(customer_notes, list) else ""
            claim_number = device_line.get("claim_number") or (ticket.properties.claim_num if ticket.properties else None)
            po_number = device_line.get("po_number") or (ticket.properties.po_num_2 if ticket.properties else None)
            student_name = ticket.properties.student if ticket.properties else None
            guardian_name = ticket.properties.p_g_name if ticket.properties else None
            guardian_phone = ticket.properties.phone_num if ticket.properties else None
            case_indicator = self._resolve_case_indicator(ticket.properties.case) if ticket.properties else None
            intake_device = intake_device_model.create(
                {
                    "intake_order": intake_order.id,
                    "device": device_record.id,
                    "claim_number": claim_number,
                    "po_number": po_number,
                    "customer_stated_notes": notes,
                    "student_name": student_name,
                    "guardian_name": guardian_name,
                    "guardian_phone": guardian_phone,
                    "needs_estimate": device_line.get("needs_estimate", False),
                    "case_indicator": case_indicator or "unknown",
                    "has_case": case_indicator == "yes" if case_indicator else False,
                }
            )
            created_lines.append(intake_device)
            summary_notes = device_line.get("summary_notes")
            if isinstance(summary_notes, list):
                summary_lines = [line.strip() for line in summary_notes if isinstance(line, str) and line.strip()]
                if summary_lines:
                    candidate = quality_control_candidates.get(device_record.id)
                    if not candidate:
                        candidate = {
                            "device": device_record,
                            "summaries": [],
                        }
                        quality_control_candidates[device_record.id] = candidate
                    summaries = candidate.get("summaries")
                    if isinstance(summaries, list):
                        for summary_line in summary_lines:
                            if summary_line not in summaries:
                                summaries.append(summary_line)

        if quality_control_candidates:
            quality_control_order_model = self.env["service.quality.control.order"].sudo().with_context(IMPORT_CONTEXT)
            quality_control_device_model = self.env["service.quality.control.order.device"].sudo().with_context(
                IMPORT_CONTEXT
            )
            finish_date = ticket.created_at
            quality_control_name = f"RepairShopr QC {ticket.id}"
            quality_control_order = quality_control_order_model.search(
                [
                    ("name", "=", quality_control_name),
                    ("client", "=", partner.id),
                ],
                limit=1,
            )
            if not quality_control_order:
                quality_control_order = quality_control_order_model.create(
                    {
                        "name": quality_control_name,
                        "state": "finished",
                        "start_date": finish_date,
                        "finish_date": finish_date,
                        "client": partner.id,
                    }
                )
            for candidate in quality_control_candidates.values():
                device_record = candidate.get("device")
                summaries = candidate.get("summaries")
                if not isinstance(device_record, models.BaseModel):
                    continue
                if not isinstance(summaries, list):
                    continue
                summary_text = "\n".join(summary for summary in summaries if isinstance(summary, str) and summary.strip())
                if not summary_text:
                    continue
                existing = quality_control_device_model.search(
                    [
                        ("quality_control_order", "=", quality_control_order.id),
                        ("device", "=", device_record.id),
                    ],
                    limit=1,
                )
                if existing:
                    existing_lines = [
                        line.strip()
                        for line in (existing.summary_note or "").splitlines()
                        if line.strip()
                    ]
                    merged_lines: list[str] = []
                    for line in [*existing_lines, *summaries]:
                        cleaned = line.strip()
                        if cleaned and cleaned not in merged_lines:
                            merged_lines.append(cleaned)
                    update_values: dict[str, object] = {}
                    merged_text = "\n".join(merged_lines)
                    if merged_text and merged_text != (existing.summary_note or ""):
                        update_values["summary_note"] = merged_text
                    if existing.state in {"pending", "started"}:
                        update_values["state"] = "passed"
                    if update_values:
                        existing.write(update_values)
                    continue
                create_values = {
                    "quality_control_order": quality_control_order.id,
                    "device": device_record.id,
                    "state": "passed",
                    "start_date": finish_date,
                    "finish_date": finish_date,
                    "summary_note": summary_text,
                }
                try:
                    with self.env.cr.savepoint():
                        quality_control_device_model.create(create_values)
                except IntegrityError:
                    existing = quality_control_device_model.search(
                        [
                            ("quality_control_order", "=", quality_control_order.id),
                            ("device", "=", device_record.id),
                        ],
                        limit=1,
                    )
                    if not existing:
                        raise
                    existing_lines = [
                        line.strip()
                        for line in (existing.summary_note or "").splitlines()
                        if line.strip()
                    ]
                    merged_lines: list[str] = []
                    for line in [*existing_lines, *summaries]:
                        cleaned = line.strip()
                        if cleaned and cleaned not in merged_lines:
                            merged_lines.append(cleaned)
                    update_values: dict[str, object] = {}
                    merged_text = "\n".join(merged_lines)
                    if merged_text and merged_text != (existing.summary_note or ""):
                        update_values["summary_note"] = merged_text
                    if existing.state in {"pending", "started"}:
                        update_values["state"] = "passed"
                    if update_values:
                        existing.write(update_values)

        return intake_order, created_lines

    def _identifier_pairs_for_ticket_link(
        self,
        identifiers: dict[str, set[str]],
    ) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        if not identifiers:
            return pairs
        for identifier_type in self._TICKET_LINK_IDENTIFIER_TYPES:
            for identifier_value in identifiers.get(identifier_type, set()):
                normalized = self._normalize_identifier_value(identifier_value)
                if normalized:
                    pairs.add((identifier_type, normalized))
        return pairs

    def _build_ticket_identifier_cache(
        self,
        identifier_pairs: set[tuple[str, str]],
    ) -> tuple[dict[tuple[str, str], set[int]], dict[int, int]]:
        if not identifier_pairs:
            return {}, {}
        identifier_types = sorted({identifier_type for identifier_type, _ in identifier_pairs})
        normalized_values = sorted({identifier_value for _, identifier_value in identifier_pairs})
        identifier_model = self.env["identifier.index"].sudo().with_context(IMPORT_CONTEXT)
        records = identifier_model.search(
            [
                ("res_model", "=", "helpdesk.ticket"),
                ("identifier_type", "in", identifier_types),
                ("identifier_normalized", "in", normalized_values),
                ("active", "=", True),
            ]
        )
        pair_to_ticket_ids: dict[tuple[str, str], set[int]] = defaultdict(set)
        candidate_ticket_ids: set[int] = set()
        for record in records:
            if not record.identifier_normalized:
                continue
            pair = (record.identifier_type, record.identifier_normalized)
            if pair not in identifier_pairs:
                continue
            pair_to_ticket_ids[pair].add(record.res_id)
            candidate_ticket_ids.add(record.res_id)
        ticket_partner_map: dict[int, int] = {}
        if candidate_ticket_ids:
            ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)
            for ticket in ticket_model.browse(list(candidate_ticket_ids)):
                if not ticket.exists():
                    continue
                ticket_partner_map[ticket.id] = ticket.partner_id.id if ticket.partner_id else 0
        return pair_to_ticket_ids, ticket_partner_map

    @staticmethod
    def _resolve_ticket_id_from_pairs(
        identifier_pairs: set[tuple[str, str]],
        *,
        pair_to_ticket_ids: dict[tuple[str, str], set[int]],
        ticket_partner_map: dict[int, int],
        partner_id: int,
    ) -> int | None:
        if not identifier_pairs or not partner_id:
            return None
        candidate_ticket_ids: set[int] = set()
        for pair in identifier_pairs:
            candidate_ticket_ids.update(pair_to_ticket_ids.get(pair, set()))
        if not candidate_ticket_ids:
            return None
        candidate_ticket_ids = {
            ticket_id
            for ticket_id in candidate_ticket_ids
            if ticket_partner_map.get(ticket_id) == partner_id
        }
        if len(candidate_ticket_ids) != 1:
            return None
        return next(iter(candidate_ticket_ids))

    _NO_CHARGE_NOTE = "repairs done at no charge"
    _pricing_catalog: "RepairshoprPricingCatalog | None" = None

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _import_estimates(
        self,
        repairshopr_client: RepairshoprSyncClient,
        start_datetime: datetime | None,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        commit_interval = self._get_commit_interval()
        processed_count = 0
        partner_cache: dict[int, int] = {}
        billing_cache: dict[int, int | None] = {}
        estimates = repairshopr_client.get_model(repairshopr_models.Estimate, updated_at=start_datetime)
        batch_size = max(commit_interval, 100)
        batch: list[repairshopr_models.Estimate] = []
        for estimate in estimates:
            batch.append(estimate)
            if len(batch) >= batch_size:
                processed_count = self._import_estimate_batch(
                    batch,
                    system,
                    sync_started_at,
                    processed_count,
                    partner_cache,
                    billing_cache,
                    repairshopr_client,
                )
                batch = []
        if batch:
            self._import_estimate_batch(
                batch,
                system,
                sync_started_at,
                processed_count,
                partner_cache,
                billing_cache,
                repairshopr_client,
            )

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _import_invoices(
        self,
        repairshopr_client: RepairshoprSyncClient,
        start_datetime: datetime | None,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        commit_interval = self._get_commit_interval()
        processed_count = 0
        sales_journal = self._get_sales_journal()
        sales_journal_id = sales_journal.id
        partner_cache: dict[int, int] = {}
        billing_cache: dict[int, int | None] = {}
        invoices = repairshopr_client.get_model(repairshopr_models.Invoice, updated_at=start_datetime)
        batch_size = max(commit_interval, 100)
        batch: list[repairshopr_models.Invoice] = []
        for invoice in invoices:
            batch.append(invoice)
            if len(batch) >= batch_size:
                processed_count = self._import_invoice_batch(
                    batch,
                    system,
                    sync_started_at,
                    processed_count,
                    partner_cache,
                    billing_cache,
                    repairshopr_client,
                    sales_journal_id,
                )
                batch = []
        if batch:
            self._import_invoice_batch(
                batch,
                system,
                sync_started_at,
                processed_count,
                partner_cache,
                billing_cache,
                repairshopr_client,
                sales_journal_id,
            )

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _import_estimate_batch(
        self,
        estimates: list[repairshopr_models.Estimate],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
        processed_count: int,
        partner_cache: dict[int, int],
        billing_cache: dict[int, int | None],
        repairshopr_client: RepairshoprSyncClient,
    ) -> int:
        estimate_by_external_id: dict[str, repairshopr_models.Estimate] = {}
        for estimate in estimates:
            external_id_value = str(estimate.id)
            existing_estimate = estimate_by_external_id.get(external_id_value)
            if not existing_estimate:
                estimate_by_external_id[external_id_value] = estimate
                continue
            existing_updated_at = existing_estimate.updated_at
            incoming_updated_at = estimate.updated_at
            if incoming_updated_at and (
                not existing_updated_at or incoming_updated_at > existing_updated_at
            ):
                estimate_by_external_id[external_id_value] = estimate
        estimates = list(estimate_by_external_id.values())
        order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        external_ids = [str(estimate.id) for estimate in estimates]
        (
            existing_map,
            stale_map,
            blocked,
            last_sync_map,
            record_map,
        ) = self._prefetch_external_id_records(
            system.id,
            RESOURCE_ESTIMATE,
            external_ids,
            "sale.order",
        )
        ticket_ids = [str(estimate.ticket_id) for estimate in estimates if estimate.ticket_id]
        (
            ticket_map,
            _,
            _,
            _,
            _,
        ) = self._prefetch_external_id_records(
            system.id,
            RESOURCE_TICKET,
            ticket_ids,
            "helpdesk.ticket",
        )
        estimate_id_values: list[int] = []
        for estimate in estimates:
            external_id_value = str(estimate.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = estimate.date or estimate.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = estimate.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            estimate_id_values.append(estimate.id)
        line_items_by_estimate_id = repairshopr_client.prefetch_estimate_line_items(estimate_id_values)
        create_values: list["odoo.values.sale_order"] = []
        create_external_ids: list[str] = []
        sync_timestamps: dict[str, datetime] = {}
        identifiers_by_external_id: dict[str, dict[str, set[str]]] = {}
        pending_commit = False
        identifier_pairs_by_external_id: dict[str, set[tuple[str, str]]] = {}
        def should_commit() -> bool:
            return commit_interval > 0 and processed_count % commit_interval == 0

        def flush_creates() -> None:
            nonlocal create_values, create_external_ids
            if not create_values:
                return
            created_records = order_model.create(create_values)
            external_id_payloads: list["odoo.values.external_id"] = []
            for created_external_id, created_order in zip(create_external_ids, created_records, strict=True):
                stale_record = stale_map.pop(created_external_id, None)
                sync_time = sync_timestamps.get(created_external_id, sync_started_at)
                if stale_record:
                    stale_record.write(
                        {
                            "res_model": "sale.order",
                            "res_id": created_order.id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                else:
                    external_id_payloads.append(
                        {
                            "res_model": "sale.order",
                            "res_id": created_order.id,
                            "system_id": system.id,
                            "resource": RESOURCE_ESTIMATE,
                            "external_id": created_external_id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                record_identifiers = identifiers_by_external_id.get(created_external_id) or {}
                if record_identifiers:
                    self._sync_identifier_index(
                        "sale.order",
                        created_order.id,
                        record_identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
            if external_id_payloads:
                self.env["external.id"].sudo().create(external_id_payloads)
            create_values = []
            create_external_ids = []

        ticket_properties_by_ticket_id = repairshopr_client.prefetch_ticket_properties_by_ticket_ids(
            [estimate.ticket_id for estimate in estimates if estimate.ticket_id]
        )
        for estimate in estimates:
            external_id_value = str(estimate.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = estimate.date or estimate.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = estimate.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            identifiers = self._collect_identifiers_from_line_items(
                line_items_by_estimate_id.get(estimate.id, [])
            )
            ticket_id = estimate.ticket_id
            if ticket_id:
                ticket_properties = ticket_properties_by_ticket_id.get(ticket_id)
                if ticket_properties:
                    identifiers = self._merge_identifier_maps(
                        identifiers,
                        self._collect_identifiers_from_ticket_properties(ticket_properties),
                    )
            identifier_pairs_by_external_id[external_id_value] = self._identifier_pairs_for_ticket_link(
                identifiers
            )
        pair_to_ticket_ids, ticket_partner_map = self._build_ticket_identifier_cache(
            {pair for pairs in identifier_pairs_by_external_id.values() for pair in pairs}
        )

        for estimate in estimates:
            external_id_value = str(estimate.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = estimate.date or estimate.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = estimate.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            partner_id = self._resolve_partner_for_customer_id(
                estimate.customer_id,
                estimate.customer_business_then_name,
                system.id,
                partner_cache,
            )
            if not partner_id:
                _logger.warning("Skipping estimate %s because partner is missing", estimate.id)
                continue
            partner = self.env["res.partner"].browse(partner_id)
            billing_contract = self._resolve_billing_contract_cached(partner, billing_cache)
            line_items = line_items_by_estimate_id.get(estimate.id, [])
            pricing_catalog = self._get_pricing_catalog()
            line_commands, identifiers = self._build_sale_order_lines(
                repairshopr_client,
                estimate.id,
                line_items=line_items,
                billing_contract=billing_contract,
                pricing_catalog=pricing_catalog,
            )
            ticket_id = estimate.ticket_id
            ticket_record_id = ticket_map.get(str(ticket_id)) if ticket_id else None
            if ticket_record_id:
                ticket_record = self.env["helpdesk.ticket"].browse(ticket_record_id)
                if ticket_record and not ticket_record.intake_order_id:
                    ticket_properties = (
                        ticket_properties_by_ticket_id.get(ticket_id)
                        if ticket_id
                        else repairshopr_models.TicketProperties()
                    )
                    intake_order, _ = self._build_intake_from_line_items(
                        ticket=repairshopr_models.Ticket(
                            id=ticket_id or 0,
                            created_at=estimate.created_at,
                            properties=ticket_properties,
                        ),
                        partner=partner,
                        line_items=line_items,
                    )
                    if intake_order:
                        ticket_record.write({"intake_order_id": intake_order.id})
            if ticket_id:
                ticket_properties = ticket_properties_by_ticket_id.get(ticket_id)
                if ticket_properties:
                    identifiers = self._merge_identifier_maps(
                        identifiers,
                        self._collect_identifiers_from_ticket_properties(ticket_properties),
                    )
            if not ticket_record_id:
                identifier_pairs = identifier_pairs_by_external_id.get(external_id_value, set())
                ticket_record_id = self._resolve_ticket_id_from_pairs(
                    identifier_pairs,
                    pair_to_ticket_ids=pair_to_ticket_ids,
                    ticket_partner_map=ticket_partner_map,
                    partner_id=partner.id,
                )
            if "source_ticket_id" in self.env["sale.order"]._fields and not ticket_record_id:
                _logger.info(
                    "Skipping estimate %s because no ticket link was found.",
                    estimate.id,
                )
                continue
            is_no_charge = self._has_no_charge_note(estimate.employee, line_items)
            line_commands = self._apply_rework_labor_adjustment(line_commands, is_no_charge, billing_contract)
            line_commands = self._prioritize_labor_lines(line_commands, billing_contract)
            order_record_id = existing_map.get(external_id_value)
            values = self._build_sale_order_values(
                estimate,
                partner,
                line_commands,
                billing_contract,
                include_line_clear=bool(order_record_id),
            )
            if ticket_record_id and "source_ticket_id" in self.env["sale.order"]._fields:
                values["source_ticket_id"] = ticket_record_id
            if estimate.number:
                identifiers.setdefault("ticket", set()).add(str(estimate.number))
            identifiers_by_external_id[external_id_value] = identifiers
            sync_timestamps[external_id_value] = updated_at or sync_started_at
            if order_record_id:
                order_record = order_model.browse(order_record_id)
                if order_record.state not in {"draft", "sent"}:
                    _logger.info("Skipping estimate %s because sale order is not editable", estimate.id)
                    continue
                order_record.write(values)
                record = record_map.get(external_id_value)
                if record:
                    record.write({"last_sync": sync_timestamps[external_id_value]})
                if identifiers:
                    self._sync_identifier_index(
                        "sale.order",
                        order_record.id,
                        identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
                processed_count += 1
                if should_commit():
                    flush_creates()
                    pending_commit = True
                if pending_commit and self._maybe_commit(processed_count, commit_interval, label="estimate"):
                    order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
                    pending_commit = False
                continue
            create_values.append(values)
            create_external_ids.append(external_id_value)
            processed_count += 1
            if should_commit():
                flush_creates()
                if self._maybe_commit(processed_count, commit_interval, label="estimate"):
                    order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)

        flush_creates()
        return processed_count

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _import_invoice_batch(
        self,
        invoices: list[repairshopr_models.Invoice],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
        processed_count: int,
        partner_cache: dict[int, int],
        billing_cache: dict[int, int | None],
        repairshopr_client: RepairshoprSyncClient,
        sales_journal_id: int,
    ) -> int:
        invoice_by_external_id: dict[str, repairshopr_models.Invoice] = {}
        for invoice in invoices:
            external_id_value = str(invoice.id)
            existing_invoice = invoice_by_external_id.get(external_id_value)
            if not existing_invoice:
                invoice_by_external_id[external_id_value] = invoice
                continue
            existing_updated_at = existing_invoice.updated_at
            incoming_updated_at = invoice.updated_at
            if incoming_updated_at and (
                not existing_updated_at or incoming_updated_at > existing_updated_at
            ):
                invoice_by_external_id[external_id_value] = invoice
        invoices = list(invoice_by_external_id.values())
        move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        external_ids = [str(invoice.id) for invoice in invoices]
        (
            existing_map,
            stale_map,
            blocked,
            last_sync_map,
            record_map,
        ) = self._prefetch_external_id_records(
            system.id,
            RESOURCE_INVOICE,
            external_ids,
            "account.move",
        )
        ticket_ids = [str(invoice.ticket_id) for invoice in invoices if invoice.ticket_id]
        (
            ticket_map,
            _,
            _,
            _,
            _,
        ) = self._prefetch_external_id_records(
            system.id,
            RESOURCE_TICKET,
            ticket_ids,
            "helpdesk.ticket",
        )
        ticket_properties_by_ticket_id = repairshopr_client.prefetch_ticket_properties_by_ticket_ids(
            [invoice.ticket_id for invoice in invoices if invoice.ticket_id]
        )
        identifier_pairs_by_external_id: dict[str, set[tuple[str, str]]] = {}
        invoice_id_values: list[int] = []
        for invoice in invoices:
            external_id_value = str(invoice.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = invoice.date or invoice.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = invoice.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            invoice_id_values.append(invoice.id)
        line_items_by_invoice_id = repairshopr_client.prefetch_invoice_line_items(invoice_id_values)
        for invoice in invoices:
            external_id_value = str(invoice.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = invoice.date or invoice.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = invoice.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            identifiers = self._collect_identifiers_from_line_items(
                line_items_by_invoice_id.get(invoice.id, [])
            )
            ticket_properties = (
                ticket_properties_by_ticket_id.get(invoice.ticket_id)
                if invoice.ticket_id
                else None
            )
            if ticket_properties:
                identifiers = self._merge_identifier_maps(
                    identifiers,
                    self._collect_identifiers_from_ticket_properties(ticket_properties),
                )
            identifier_pairs_by_external_id[external_id_value] = self._identifier_pairs_for_ticket_link(
                identifiers
            )
        pair_to_ticket_ids, ticket_partner_map = self._build_ticket_identifier_cache(
            {pair for pairs in identifier_pairs_by_external_id.values() for pair in pairs}
        )
        create_values: list["odoo.values.account_move"] = []
        create_external_ids: list[str] = []
        sync_timestamps: dict[str, datetime] = {}
        identifiers_by_external_id: dict[str, dict[str, set[str]]] = {}
        pending_commit = False

        def should_commit() -> bool:
            return commit_interval > 0 and processed_count % commit_interval == 0

        def flush_creates() -> None:
            nonlocal create_values, create_external_ids
            if not create_values:
                return
            created_records = move_model.create(create_values)
            external_id_payloads: list["odoo.values.external_id"] = []
            for created_external_id, created_move in zip(create_external_ids, created_records, strict=True):
                stale_record = stale_map.pop(created_external_id, None)
                sync_time = sync_timestamps.get(created_external_id, sync_started_at)
                if stale_record:
                    stale_record.write(
                        {
                            "res_model": "account.move",
                            "res_id": created_move.id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                else:
                    external_id_payloads.append(
                        {
                            "res_model": "account.move",
                            "res_id": created_move.id,
                            "system_id": system.id,
                            "resource": RESOURCE_INVOICE,
                            "external_id": created_external_id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                record_identifiers = identifiers_by_external_id.get(created_external_id) or {}
                if record_identifiers:
                    self._sync_identifier_index(
                        "account.move",
                        created_move.id,
                        record_identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
            if external_id_payloads:
                self.env["external.id"].sudo().create(external_id_payloads)
            create_values = []
            create_external_ids = []

        sales_journal = self.env["account.journal"].browse(sales_journal_id)
        for invoice in invoices:
            external_id_value = str(invoice.id)
            if external_id_value in blocked:
                continue
            cutoff_timestamp = invoice.date or invoice.created_at
            if self._is_before_transaction_cutoff(cutoff_timestamp):
                continue
            updated_at = invoice.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            partner_id = self._resolve_partner_for_customer_id(
                invoice.customer_id,
                invoice.customer_business_then_name,
                system.id,
                partner_cache,
            )
            if not partner_id:
                _logger.warning("Skipping invoice %s because partner is missing", invoice.id)
                continue
            partner = self.env["res.partner"].browse(partner_id)
            billing_contract = self._resolve_billing_contract_cached(partner, billing_cache)
            line_items = line_items_by_invoice_id.get(invoice.id, [])
            pricing_catalog = self._get_pricing_catalog()
            line_commands, identifiers = self._build_invoice_lines(
                repairshopr_client,
                invoice.id,
                line_items=line_items,
                billing_contract=billing_contract,
                pricing_catalog=pricing_catalog,
            )
            ticket_properties = (
                ticket_properties_by_ticket_id.get(invoice.ticket_id)
                if invoice.ticket_id
                else None
            )
            if ticket_properties:
                identifiers = self._merge_identifier_maps(
                    identifiers,
                    self._collect_identifiers_from_ticket_properties(ticket_properties),
                )
            is_no_charge = self._has_no_charge_note(invoice.note, line_items)
            line_commands = self._apply_rework_labor_adjustment(line_commands, is_no_charge, billing_contract)
            line_commands = self._prioritize_labor_lines(line_commands, billing_contract)
            move_record_id = existing_map.get(external_id_value)
            values = self._build_invoice_values(
                invoice,
                partner,
                line_commands,
                sales_journal,
                billing_contract,
                include_line_clear=bool(move_record_id),
            )
            ticket_record_id = ticket_map.get(str(invoice.ticket_id)) if invoice.ticket_id else None
            if ticket_record_id:
                values["source_ticket_id"] = ticket_record_id
            if not values.get("source_ticket_id"):
                identifier_pairs = identifier_pairs_by_external_id.get(external_id_value, set())
                ticket_record_id = self._resolve_ticket_id_from_pairs(
                    identifier_pairs,
                    pair_to_ticket_ids=pair_to_ticket_ids,
                    ticket_partner_map=ticket_partner_map,
                    partner_id=partner.id,
                )
                if ticket_record_id:
                    values["source_ticket_id"] = ticket_record_id
            if "source_ticket_id" in self.env["account.move"]._fields and not values.get("source_ticket_id"):
                _logger.info(
                    "Skipping invoice %s because no ticket link was found.",
                    invoice.id,
                )
                continue
            if invoice.number:
                identifiers.setdefault("invoice", set()).add(str(invoice.number))
            identifiers_by_external_id[external_id_value] = identifiers
            sync_timestamps[external_id_value] = updated_at or sync_started_at
            if move_record_id:
                move_record = move_model.browse(move_record_id)
                if move_record.state != "draft":
                    _logger.info("Skipping invoice %s because account move is not editable", invoice.id)
                    continue
                move_record.write(values)
                record = record_map.get(external_id_value)
                if record:
                    record.write({"last_sync": sync_timestamps[external_id_value]})
                if identifiers:
                    self._sync_identifier_index(
                        "account.move",
                        move_record.id,
                        identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
                processed_count += 1
                if should_commit():
                    flush_creates()
                    pending_commit = True
                if pending_commit and self._maybe_commit(processed_count, commit_interval, label="invoice"):
                    move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
                    sales_journal = self.env["account.journal"].browse(sales_journal_id)
                    pending_commit = False
                continue
            create_values.append(values)
            create_external_ids.append(external_id_value)
            processed_count += 1
            if should_commit():
                flush_creates()
                if self._maybe_commit(processed_count, commit_interval, label="invoice"):
                    move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
                    sales_journal = self.env["account.journal"].browse(sales_journal_id)

        flush_creates()
        return processed_count

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_sale_order_values(
        self,
        estimate: repairshopr_models.Estimate,
        partner: "odoo.model.res_partner",
        line_commands: list[tuple],
        billing_contract: "odoo.model.school_billing_contract | None",
        *,
        include_line_clear: bool,
    ) -> "odoo.values.sale_order":
        order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        default_values = order_model.default_get(
            ["pricelist_id", "company_id", "team_id", "user_id"]
        )
        order_lines = list(line_commands)
        if include_line_clear:
            order_lines = [(5, 0, 0)] + order_lines
        values = {
            **default_values,
            "partner_id": partner.id,
            "client_order_ref": estimate.number or "",
            "date_order": estimate.date or estimate.created_at or fields.Datetime.now(),
            "order_line": order_lines,
        }
        if billing_contract and "billing_contract_id" in self.env["sale.order"]._fields:
            values["billing_contract_id"] = billing_contract.id
            if billing_contract.pricelist_id:
                values["pricelist_id"] = billing_contract.pricelist_id.id
        if estimate.employee:
            values["note"] = estimate.employee
        return values

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_invoice_values(
        self,
        invoice: repairshopr_models.Invoice,
        partner: "odoo.model.res_partner",
        line_commands: list[tuple],
        sales_journal: "odoo.model.account_journal",
        billing_contract: "odoo.model.school_billing_contract | None",
        *,
        include_line_clear: bool,
    ) -> "odoo.values.account_move":
        move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
        default_values = move_model.default_get(["currency_id", "company_id"])
        invoice_lines = list(line_commands)
        if include_line_clear:
            invoice_lines = [(5, 0, 0)] + invoice_lines
        values = {
            **default_values,
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": invoice.date or invoice.created_at or fields.Datetime.now(),
            "invoice_date_due": invoice.due_date or invoice.date or invoice.created_at,
            "ref": invoice.number or "",
            "invoice_origin": f"RepairShopr Invoice {invoice.id}",
            "journal_id": sales_journal.id,
            "invoice_line_ids": invoice_lines,
        }
        if billing_contract and "billing_contract_id" in self.env["account.move"]._fields:
            values["billing_contract_id"] = billing_contract.id
        if invoice.note:
            values["narration"] = invoice.note
        return values

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_sale_order_lines(
        self,
        repairshopr_client: RepairshoprSyncClient,
        estimate_id: int | None,
        *,
        line_items: list[dict[str, Any]] | None = None,
        billing_contract: "odoo.model.school_billing_contract | None",
        pricing_catalog: "RepairshoprPricingCatalog",
    ) -> tuple[list[tuple], dict[str, set[str]]]:
        if line_items is None:
            line_items = self._fetch_line_items(repairshopr_client, estimate_id=estimate_id)
        identifiers = self._collect_identifiers_from_line_items(line_items)
        line_commands: list[tuple] = []
        for line_item_data in line_items:
            line_values = self._build_sale_order_line_values(
                line_item_data,
                billing_contract=billing_contract,
                pricing_catalog=pricing_catalog,
            )
            if line_values:
                line_commands.append((0, 0, line_values))
        return line_commands, identifiers

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_invoice_lines(
        self,
        repairshopr_client: RepairshoprSyncClient,
        invoice_id: int | None,
        *,
        line_items: list[dict[str, Any]] | None = None,
        billing_contract: "odoo.model.school_billing_contract | None",
        pricing_catalog: "RepairshoprPricingCatalog",
    ) -> tuple[list[tuple], dict[str, set[str]]]:
        if line_items is None:
            line_items = self._fetch_line_items(repairshopr_client, invoice_id=invoice_id)
        identifiers = self._collect_identifiers_from_line_items(line_items)
        line_commands: list[tuple] = []
        for line_item_data in line_items:
            line_values = self._build_invoice_line_values(
                line_item_data,
                billing_contract=billing_contract,
                pricing_catalog=pricing_catalog,
            )
            if line_values:
                line_commands.append((0, 0, line_values))
        return line_commands, identifiers

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_sale_order_line_values(
        self,
        line_item_data: dict[str, Any],
        *,
        billing_contract: "odoo.model.school_billing_contract | None",
        pricing_catalog: "RepairshoprPricingCatalog",
    ) -> "odoo.values.sale_order_line":
        product_record = self._get_product_variant_for_line_item(
            line_item_data.get("product_id"),
            line_item_data.get("name") or line_item_data.get("item"),
        )
        quantity = self._to_float(line_item_data.get("quantity"), default=1.0)
        price = self._to_float(line_item_data.get("price"), default=0.0)
        discount = self._to_float(line_item_data.get("discount_percent"), default=0.0)
        name = line_item_data.get("name") or line_item_data.get("item") or product_record.display_name
        pricing_override = self._resolve_pricing_override(
            line_item_data,
            billing_contract,
            pricing_catalog,
        )
        if pricing_override is not None:
            price = pricing_override
        values = {
            "product_id": product_record.id,
            "name": name,
            "product_uom_qty": quantity,
            "price_unit": price,
        }
        if discount:
            values["discount"] = discount
        return values

    # noinspection DuplicatedCode
    # Estimates/invoices run in parallel for clarity; abstraction would hide model-specific rules.
    def _build_invoice_line_values(
        self,
        line_item_data: dict[str, Any],
        *,
        billing_contract: "odoo.model.school_billing_contract | None",
        pricing_catalog: "RepairshoprPricingCatalog",
    ) -> "odoo.values.account_move_line":
        product_record = self._get_product_variant_for_line_item(
            line_item_data.get("product_id"),
            line_item_data.get("name") or line_item_data.get("item"),
        )
        quantity = self._to_float(line_item_data.get("quantity"), default=1.0)
        price = self._to_float(line_item_data.get("price"), default=0.0)
        name = line_item_data.get("name") or line_item_data.get("item") or product_record.display_name
        pricing_override = self._resolve_pricing_override(
            line_item_data,
            billing_contract,
            pricing_catalog,
        )
        if pricing_override is not None:
            price = pricing_override
        values = {
            "product_id": product_record.id,
            "name": name,
            "quantity": quantity,
            "price_unit": price,
        }
        return values

    def _prioritize_labor_lines(
        self,
        line_commands: list[tuple],
        billing_contract: "odoo.model.school_billing_contract | None",
    ) -> list[tuple]:
        if not line_commands or not billing_contract:
            return line_commands
        policy = billing_contract.policy_id
        if not policy:
            return line_commands
        labor_product = policy.labor_product_id
        labor_line_commands: list[tuple] = []
        other_line_commands: list[tuple] = []
        for line_command in line_commands:
            if self._is_labor_line_command(line_command, labor_product):
                labor_line_commands.append(line_command)
                continue
            other_line_commands.append(line_command)
        if labor_product and not labor_line_commands:
            _logger.info(
                "RepairShopr import: no labor line found for billing contract %s (policy %s)",
                billing_contract.display_name,
                policy.display_name,
            )
        if not labor_line_commands:
            return line_commands
        return labor_line_commands + other_line_commands

    def _apply_rework_labor_adjustment(
        self,
        line_commands: list[tuple],
        is_no_charge: bool,
        billing_contract: "odoo.model.school_billing_contract | None",
    ) -> list[tuple]:
        if not is_no_charge or not line_commands or not billing_contract:
            return line_commands
        policy = billing_contract.policy_id
        if not policy:
            return line_commands
        labor_product = policy.labor_product_id
        adjusted_line_commands: list[tuple] = []
        labor_adjustment_applied = False
        for line_command in line_commands:
            if labor_adjustment_applied or not self._is_labor_line_command(line_command, labor_product):
                adjusted_line_commands.append(line_command)
                continue
            adjusted_line_command = self._decrement_line_quantity(line_command)
            if adjusted_line_command is None:
                labor_adjustment_applied = True
                continue
            if adjusted_line_command != line_command:
                labor_adjustment_applied = True
            adjusted_line_commands.append(adjusted_line_command)
        return adjusted_line_commands

    @staticmethod
    def _is_labor_line_command(
        line_command: tuple,
        labor_product: "odoo.model.product_product | None",
    ) -> bool:
        if len(line_command) < 3:
            return False
        line_values = line_command[2]
        if not isinstance(line_values, dict):
            return False
        product_id = line_values.get("product_id")
        if labor_product and product_id == labor_product.id:
            return True
        name = str(line_values.get("name") or "").strip().lower()
        return "labor" in name

    def _decrement_line_quantity(self, line_command: tuple) -> tuple | None:
        if len(line_command) < 3:
            return line_command
        line_values = line_command[2]
        if not isinstance(line_values, dict):
            return line_command
        quantity_key = None
        if "product_uom_qty" in line_values:
            quantity_key = "product_uom_qty"
        elif "quantity" in line_values:
            quantity_key = "quantity"
        if not quantity_key:
            return line_command
        quantity_value = self._to_float(line_values.get(quantity_key), default=0.0)
        if quantity_value <= 1:
            return None
        updated_values = dict(line_values)
        updated_values[quantity_key] = quantity_value - 1
        return line_command[0], line_command[1], updated_values

    def _has_no_charge_note(
        self,
        header_note: str | None,
        line_items: list[dict[str, Any]],
    ) -> bool:
        note_value = (header_note or "").strip().lower()
        if self._NO_CHARGE_NOTE in note_value:
            return True
        for line_item in line_items:
            for key in ("name", "item"):
                text_value = str(line_item.get(key) or "").strip().lower()
                if self._NO_CHARGE_NOTE in text_value:
                    return True
        return False

    def _resolve_pricing_override(
        self,
        line_item_data: dict[str, Any],
        billing_contract: "odoo.model.school_billing_contract | None",
        pricing_catalog: "RepairshoprPricingCatalog",
    ) -> float | None:
        if not billing_contract:
            return None
        catalog_key = pricing_catalog.select_catalog(billing_contract)
        if not catalog_key:
            return None
        model_key, repair_key = self._split_model_repair(line_item_data)
        if not model_key or not repair_key:
            return None
        return pricing_catalog.get_price(catalog_key, model_key, repair_key)

    @staticmethod
    def _split_model_repair(line_item_data: dict[str, Any]) -> tuple[str | None, str | None]:
        candidate_texts = [line_item_data.get("name"), line_item_data.get("item")]
        for candidate in candidate_texts:
            raw_text = str(candidate or "").strip()
            if not raw_text:
                continue
            separator = " - "
            if separator in raw_text:
                model_text, repair_text = raw_text.split(separator, 1)
                return (
                    RepairshoprPricingCatalog.normalize_model(model_text),
                    RepairshoprPricingCatalog.normalize_repair(repair_text),
                )
        return None, None

    def _get_pricing_catalog(self) -> "RepairshoprPricingCatalog":
        catalog = type(self)._pricing_catalog
        if catalog is None:
            catalog = RepairshoprPricingCatalog.load()
            type(self)._pricing_catalog = catalog
        return catalog

    @staticmethod
    def _fetch_line_items(
        repairshopr_client: RepairshoprSyncClient,
        *,
        estimate_id: int | None = None,
        invoice_id: int | None = None,
    ) -> list[dict[str, Any]]:
        line_items = repairshopr_client.fetch_line_items(estimate_id=estimate_id, invoice_id=invoice_id)
        return list(line_items or [])

    def _get_sales_journal(self) -> "odoo.model.account_journal":
        journal = self.env["account.journal"].sudo().search([("type", "=", "sale")], limit=1)
        if not journal:
            raise UserError("Sales journal not found; configure accounting before importing invoices.")
        return journal

    @staticmethod
    def _to_float(value: Any, *, default: float) -> float:
        try:
            return float(value) if value not in (None, "") else default
        except (TypeError, ValueError):
            return default


class RepairshoprPricingCatalog:
    _PRICE_COLUMN_PATTERNS = ("price", "pricing")
    _EXCLUDED_PRICE_COLUMN_TOKENS = ("%", "percent", "pct", "markup", "difference")
    _VALUE_STRIP = re.compile(r"[^0-9.\-]")
    _PARENTHETICAL = re.compile(r"\([^)]*\)")
    _REPAIR_SUFFIX = re.compile(r"\b(replacement|replace|repair)\b", re.IGNORECASE)

    def __init__(self, catalogs: dict[str, dict[tuple[str, str], float]]) -> None:
        self._catalogs = catalogs

    @classmethod
    def load(cls) -> "RepairshoprPricingCatalog":
        module_path = Path(__file__).resolve()
        repo_root = None
        for parent in module_path.parents:
            if (parent / "pyproject.toml").exists():
                repo_root = parent
                break
        if repo_root is None:
            repo_root = module_path.parents[3]
        data_root = repo_root / "docs" / "internal" / "data"
        catalogs: dict[str, dict[tuple[str, str], float]] = {}
        if not data_root.exists():
            _logger.info("RepairShopr pricing catalog not found at %s", data_root)
            return cls(catalogs)

        regular_catalog = cls._load_regular_catalog(data_root)
        catalogs["regular"] = regular_catalog
        catalogs["esboces"] = cls._load_esboces_catalog(data_root)
        catalogs["nassau"] = cls._load_nassau_catalog(data_root)
        catalogs["stamford"] = cls._merge_overrides(
            regular_catalog,
            cls._load_difference_catalog(data_root, "Stamford Pricing Differences"),
        )
        catalogs["new_rochelle"] = cls._merge_overrides(
            regular_catalog,
            cls._load_difference_catalog(data_root, "New Rochelle Pricing Differences"),
        )
        return cls(catalogs)

    @staticmethod
    def select_catalog(billing_contract: "odoo.model.school_billing_contract") -> str | None:
        policy = billing_contract.policy_id
        policy_code = (policy.code or "").strip().lower() if policy else ""
        policy_name = (policy.name or "").strip().lower() if policy else ""
        partner_name = (billing_contract.partner_id.name or "").strip().lower()
        label = " ".join(value for value in (policy_code, policy_name, partner_name) if value)
        if "worth ave" in label or "wag" in label:
            return None
        if "esboces" in label or "eastern suffolk boces" in label:
            return "esboces"
        if "nassau" in label and "boces" in label:
            return "nassau"
        if "stamford" in label:
            return "stamford"
        if "new rochelle" in label:
            return "new_rochelle"
        return "regular"

    def get_price(self, catalog_key: str, model_key: str, repair_key: str) -> float | None:
        catalog = self._catalogs.get(catalog_key)
        if not catalog:
            return None
        return catalog.get((model_key, repair_key))

    @classmethod
    def _load_regular_catalog(cls, data_root: Path) -> dict[tuple[str, str], float]:
        return cls._load_catalog_from_prefix(data_root, "Reg ", preferred_columns=["price"])

    @classmethod
    def _load_esboces_catalog(cls, data_root: Path) -> dict[tuple[str, str], float]:
        return cls._load_catalog_from_prefix(data_root, "ESBOCES ", preferred_columns=["price"])

    @classmethod
    def _load_nassau_catalog(cls, data_root: Path) -> dict[tuple[str, str], float]:
        return cls._load_catalog_from_prefix(data_root, "Nassau BOCES ", preferred_columns=["price"])

    @classmethod
    def _load_difference_catalog(cls, data_root: Path, prefix: str) -> dict[tuple[str, str], float]:
        return cls._load_catalog_from_prefix(data_root, prefix, preferred_columns=["pricing", "price"])

    @classmethod
    def _load_catalog_from_prefix(
        cls,
        data_root: Path,
        prefix: str,
        *,
        preferred_columns: list[str],
    ) -> dict[tuple[str, str], float]:
        catalog: dict[tuple[str, str], float] = {}
        for path in sorted(data_root.glob(f"{prefix}*.csv")):
            catalog.update(cls._load_catalog_file(path, preferred_columns))
        return catalog

    @classmethod
    def _merge_overrides(
        cls,
        base_catalog: dict[tuple[str, str], float],
        override_catalog: dict[tuple[str, str], float],
    ) -> dict[tuple[str, str], float]:
        merged = dict(base_catalog)
        merged.update(override_catalog)
        return merged

    @classmethod
    def _load_catalog_file(
        cls,
        path: Path,
        preferred_columns: list[str],
    ) -> dict[tuple[str, str], float]:
        catalog: dict[tuple[str, str], float] = {}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            headers = next(reader, [])
            if not headers:
                return catalog
            column_names = cls._dedupe_headers(headers)
            for row in reader:
                if not row or all(not (cell or "").strip() for cell in row):
                    continue
                row_map = {column_names[index]: value for index, value in enumerate(row) if index < len(column_names)}
                model_raw = row_map.get("model") or row_map.get("Model")
                repair_raw = row_map.get("repair") or row_map.get("Repair")
                model_key = cls.normalize_model(model_raw)
                repair_key = cls.normalize_repair(repair_raw)
                if not model_key or not repair_key:
                    continue
                price_value = cls._extract_price(row_map, preferred_columns)
                if price_value is None:
                    continue
                catalog[(model_key, repair_key)] = price_value
        return catalog

    @classmethod
    def _extract_price(cls, row_map: dict[str, str], preferred_columns: list[str]) -> float | None:
        for preferred in preferred_columns:
            normalized_preferred = preferred.strip().lower()
            duplicate_prefix = f"{normalized_preferred}__"
            exact_values: list[float] = []
            for key, value in row_map.items():
                normalized_key = key.strip().lower()
                if normalized_key == normalized_preferred:
                    pass
                elif normalized_key.startswith(duplicate_prefix):
                    suffix = normalized_key.removeprefix(duplicate_prefix)
                    if not suffix.isdigit():
                        continue
                else:
                    continue
                if cls._is_excluded_price_column(normalized_key):
                    continue
                parsed = cls._parse_price(value)
                if parsed is not None:
                    exact_values.append(parsed)
            if exact_values:
                return min(exact_values)

            preferred_values: list[float] = []
            for key, value in row_map.items():
                normalized_key = key.strip().lower()
                if normalized_preferred not in normalized_key:
                    continue
                if cls._is_excluded_price_column(normalized_key):
                    continue
                parsed = cls._parse_price(value)
                if parsed is not None:
                    preferred_values.append(parsed)
            if preferred_values:
                return min(preferred_values)
        parsed_values: list[float] = []
        for key, value in row_map.items():
            normalized_key = key.strip().lower()
            if cls._is_excluded_price_column(normalized_key):
                continue
            if not cls._is_price_column(normalized_key):
                continue
            parsed = cls._parse_price(value)
            if parsed is not None:
                parsed_values.append(parsed)
        return min(parsed_values) if parsed_values else None

    @classmethod
    def _parse_price(cls, value: str | None) -> float | None:
        if not value:
            return None
        cleaned = cls._VALUE_STRIP.sub("", value)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @classmethod
    def _dedupe_headers(cls, headers: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        deduped: list[str] = []
        for header in headers:
            name = header.strip()
            if not name:
                name = "column"
            normalized = name
            count = seen.get(normalized, 0)
            seen[normalized] = count + 1
            if count:
                normalized = f"{normalized}__{count + 1}"
            deduped.append(normalized)
        return deduped

    @classmethod
    def _is_price_column(cls, key: str) -> bool:
        lower_key = key.lower()
        return any(pattern in lower_key for pattern in cls._PRICE_COLUMN_PATTERNS)

    @classmethod
    def _is_excluded_price_column(cls, key: str) -> bool:
        lower_key = key.lower()
        return any(token in lower_key for token in cls._EXCLUDED_PRICE_COLUMN_TOKENS)

    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = cls._PARENTHETICAL.sub("", value)
        return cls._normalize_key(cleaned)

    @classmethod
    def normalize_repair(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = cls._PARENTHETICAL.sub("", value)
        cleaned = cls._REPAIR_SUFFIX.sub("", cleaned)
        return cls._normalize_key(cleaned)

    @staticmethod
    def _normalize_key(value: str) -> str:
        cleaned = value.replace("&", "and")
        cleaned = " ".join(cleaned.strip().lower().split())
        return cleaned or ""
