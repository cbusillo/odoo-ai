from datetime import datetime

from odoo import models

from ..services import repairshopr_sync_models as repairshopr_models
from ..services.repairshopr_sync_client import RepairshoprSyncClient
from .repairshopr_importer import DEFAULT_HELPDESK_TEAM_NAME, EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_TICKET


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_tickets(
        self,
        repairshopr_client: RepairshoprSyncClient,
        start_datetime: datetime | None,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        commit_interval = self._get_commit_interval()
        processed_count = 0
        helpdesk_team = self._get_helpdesk_team()
        helpdesk_team_id = helpdesk_team.id
        stage_cache: dict[str, int] = {}
        tag_cache: dict[str, int] = {}
        partner_cache: dict[int, int] = {}
        billing_cache: dict[int, int | None] = {}
        tickets = repairshopr_client.get_model(repairshopr_models.Ticket, updated_at=start_datetime)
        batch_size = max(commit_interval, 200)
        batch: list[repairshopr_models.Ticket] = []
        for ticket in tickets:
            batch.append(ticket)
            if len(batch) >= batch_size:
                processed_count = self._import_ticket_batch(
                    batch,
                    system,
                    sync_started_at,
                    processed_count,
                    helpdesk_team_id,
                    stage_cache,
                    tag_cache,
                    partner_cache,
                    billing_cache,
                )
                batch = []
        if batch:
            self._import_ticket_batch(
                batch,
                system,
                sync_started_at,
                processed_count,
                helpdesk_team_id,
                stage_cache,
                tag_cache,
                partner_cache,
                billing_cache,
            )

    # noinspection DuplicatedCode
    # Ticket import flow mirrors sales batch patterns; keeping it explicit aids debugging.
    def _import_ticket_batch(
        self,
        tickets: list[repairshopr_models.Ticket],
        system: "odoo.model.external_system",
        sync_started_at: datetime,
        processed_count: int,
        helpdesk_team_id: int,
        stage_cache: dict[str, int],
        tag_cache: dict[str, int],
        partner_cache: dict[int, int],
        billing_cache: dict[int, int | None],
    ) -> int:
        ticket_by_external_id: dict[str, repairshopr_models.Ticket] = {}
        for ticket in tickets:
            external_id_value = str(ticket.id)
            existing_ticket = ticket_by_external_id.get(external_id_value)
            if not existing_ticket:
                ticket_by_external_id[external_id_value] = ticket
                continue
            existing_updated_at = existing_ticket.updated_at
            incoming_updated_at = ticket.updated_at
            if incoming_updated_at and (not existing_updated_at or incoming_updated_at > existing_updated_at):
                ticket_by_external_id[external_id_value] = ticket
        tickets = list(ticket_by_external_id.values())
        ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        external_ids = [str(ticket.id) for ticket in tickets]
        (
            existing_map,
            stale_map,
            blocked,
            last_sync_map,
            record_map,
        ) = self._prefetch_external_id_records(
            system.id,
            RESOURCE_TICKET,
            external_ids,
            "helpdesk.ticket",
        )
        create_values: list["odoo.values.helpdesk_ticket"] = []
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
            created_records = ticket_model.create(create_values)
            external_id_payloads: list["odoo.values.external_id"] = []
            for created_external_id, created_ticket in zip(create_external_ids, created_records, strict=True):
                stale_record = stale_map.pop(created_external_id, None)
                sync_time = sync_timestamps.get(created_external_id, sync_started_at)
                if stale_record:
                    stale_record.write(
                        {
                            "res_model": "helpdesk.ticket",
                            "res_id": created_ticket.id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                else:
                    external_id_payloads.append(
                        {
                            "res_model": "helpdesk.ticket",
                            "res_id": created_ticket.id,
                            "system_id": system.id,
                            "resource": RESOURCE_TICKET,
                            "external_id": created_external_id,
                            "active": True,
                            "last_sync": sync_time,
                        }
                    )
                record_identifiers = identifiers_by_external_id.get(created_external_id) or {}
                if record_identifiers:
                    self._sync_identifier_index(
                        "helpdesk.ticket",
                        created_ticket.id,
                        record_identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
            if external_id_payloads:
                self.env["external.id"].sudo().create(external_id_payloads)
            create_values = []
            create_external_ids = []

        for ticket in tickets:
            external_id_value = str(ticket.id)
            if external_id_value in blocked:
                continue
            updated_at = ticket.updated_at
            last_sync = last_sync_map.get(external_id_value)
            if updated_at and last_sync and last_sync >= updated_at:
                continue
            partner_id = self._resolve_partner_for_customer_id(
                ticket.customer_id,
                ticket.customer_business_then_name,
                system.id,
                partner_cache,
            )
            partner = self.env["res.partner"].browse(partner_id) if partner_id else self.env["res.partner"].browse()
            billing_contract = self._resolve_billing_contract_cached(partner, billing_cache)
            values = self._build_ticket_values(
                ticket,
                partner,
                helpdesk_team_id,
                billing_contract,
                stage_cache=stage_cache,
                tag_cache=tag_cache,
            )
            property_values, identifiers = self._build_ticket_property_values(ticket)
            values.update(property_values)
            identifiers_by_external_id[external_id_value] = identifiers
            sync_timestamps[external_id_value] = updated_at or sync_started_at
            existing_ticket_id = existing_map.get(external_id_value)
            if existing_ticket_id:
                ticket_record = ticket_model.browse(existing_ticket_id)
                ticket_record.write(values)
                record = record_map.get(external_id_value)
                if record:
                    record.write({"last_sync": sync_timestamps[external_id_value]})
                if identifiers:
                    self._sync_identifier_index(
                        "helpdesk.ticket",
                        ticket_record.id,
                        identifiers,
                        source_system=EXTERNAL_SYSTEM_CODE,
                    )
                processed_count += 1
                if should_commit():
                    flush_creates()
                    pending_commit = True
                if pending_commit and self._maybe_commit(processed_count, commit_interval, label="ticket"):
                    ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)
                    pending_commit = False
                continue
            create_values.append(values)
            create_external_ids.append(external_id_value)
            processed_count += 1
            if should_commit():
                flush_creates()
                if self._maybe_commit(processed_count, commit_interval, label="ticket"):
                    ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)

        flush_creates()
        return processed_count

    def _build_ticket_values(
        self,
        ticket: repairshopr_models.Ticket,
        partner: "odoo.model.res_partner",
        helpdesk_team_id: int,
        billing_contract: "odoo.model.school_billing_contract | None",
        *,
        stage_cache: dict[str, int],
        tag_cache: dict[str, int],
    ) -> "odoo.values.helpdesk_ticket":
        name = ticket.subject or f"RepairShopr Ticket {ticket.number or ticket.id}"
        values: "odoo.values.helpdesk_ticket" = {
            "name": name,
            "team_id": helpdesk_team_id,
            "description": self._compose_ticket_description(ticket),
        }
        if partner:
            values["partner_id"] = partner.id
        if billing_contract and "billing_contract_id" in self.env["helpdesk.ticket"]._fields:
            values["billing_contract_id"] = billing_contract.id
        if ticket.status:
            stage_id = self._get_or_create_helpdesk_stage_cached(helpdesk_team_id, ticket.status, stage_cache)
            if stage_id:
                values["stage_id"] = stage_id
        if "priority" in self.env["helpdesk.ticket"]._fields and ticket.priority:
            values["priority"] = ticket.priority
        if "tag_ids" in self.env["helpdesk.ticket"]._fields and ticket.problem_type:
            tag_ids = self._get_or_create_helpdesk_tags_cached([ticket.problem_type], tag_cache)
            if tag_ids:
                values["tag_ids"] = [(6, 0, tag_ids)]
        return values

    def _get_or_create_helpdesk_stage_cached(
        self,
        helpdesk_team_id: int,
        status_name: str,
        stage_cache: dict[str, int],
    ) -> int | None:
        normalized = (status_name or "").strip()
        if not normalized:
            return None
        cached_id = stage_cache.get(normalized)
        if cached_id:
            return cached_id
        stage_model = self.env["helpdesk.stage"].sudo().with_context(IMPORT_CONTEXT)
        stage = stage_model.search(
            [
                ("name", "=", normalized),
                ("team_ids", "in", helpdesk_team_id),
            ],
            limit=1,
        )
        if not stage:
            default_values = stage_model.default_get(["legend_blocked", "legend_done", "legend_normal", "sequence"])
            values = {
                **default_values,
                "name": normalized,
                "team_ids": [(6, 0, [helpdesk_team_id])],
            }
            stage = stage_model.create(values)
        stage_cache[normalized] = stage.id
        return stage.id

    def _get_or_create_helpdesk_tags_cached(
        self,
        names: list[str],
        tag_cache: dict[str, int],
    ) -> list[int]:
        if not names:
            return []
        tag_model = self.env["helpdesk.tag"].sudo().with_context(IMPORT_CONTEXT)
        tag_ids: list[int] = []
        for name in names:
            normalized = (name or "").strip()
            if not normalized:
                continue
            cached_id = tag_cache.get(normalized)
            if cached_id:
                tag_ids.append(cached_id)
                continue
            tag = tag_model.search([("name", "=", normalized)], limit=1)
            if not tag:
                tag = tag_model.create({"name": normalized})
            tag_cache[normalized] = tag.id
            tag_ids.append(tag.id)
        return tag_ids

    def _build_ticket_property_values(
        self,
        ticket: repairshopr_models.Ticket,
    ) -> tuple[dict[str, object], dict[str, set[str]]]:
        values: dict[str, object] = {}
        identifiers = self._collect_identifiers_from_ticket_properties(ticket.properties)
        ticket_number = ticket.number
        if ticket_number:
            identifiers.setdefault("ticket", set()).add(str(ticket_number))
        if ticket.properties:
            claim_number = ticket.properties.claim_num
            if claim_number:
                values["claim_number"] = claim_number
            call_number = ticket.properties.call_num
            if call_number:
                values["call_number"] = call_number
            delivery_number = ticket.properties.delivery_num
            if delivery_number:
                values["delivery_number"] = delivery_number
            raw_location = ticket.properties.location or ticket.properties.boces
            if raw_location:
                values["location_raw"] = raw_location
                values["location_label"] = raw_location
                values["location_normalized"] = self._normalize_location_value(raw_location)
            transport_value = ticket.properties.transport
            if transport_value:
                values["transport_location_label"] = transport_value
            transport_secondary = ticket.properties.transport_2
            if transport_secondary:
                values["transport_location_2_label"] = transport_secondary
            dropoff_location = ticket.properties.drop_off_location
            if dropoff_location:
                values["dropoff_location_label"] = dropoff_location
        return values, identifiers

    @staticmethod
    def _normalize_location_value(value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _get_helpdesk_team(self) -> "odoo.model.helpdesk_team":
        team_model = self.env["helpdesk.team"].sudo().with_context(IMPORT_CONTEXT)
        team = team_model.search([("name", "=", DEFAULT_HELPDESK_TEAM_NAME)], limit=1)
        if team:
            return team
        default_values = team_model.default_get(["assign_method", "privacy_visibility", "company_id", "member_ids"])
        if not default_values.get("company_id"):
            default_values["company_id"] = self.env.company.id
        if not default_values.get("member_ids"):
            default_values["member_ids"] = [(6, 0, [self.env.user.id])]
        values = {
            **default_values,
            "name": DEFAULT_HELPDESK_TEAM_NAME,
        }
        return team_model.create(values)

    def _get_helpdesk_stage(
        self,
        helpdesk_team: "odoo.model.helpdesk_team",
        status_name: str,
    ) -> "odoo.model.helpdesk_stage":
        stage_model = self.env["helpdesk.stage"].sudo().with_context(IMPORT_CONTEXT)
        stage = stage_model.search(
            [
                ("name", "=", status_name),
                ("team_ids", "in", helpdesk_team.id),
            ],
            limit=1,
        )
        if stage:
            return stage
        default_values = stage_model.default_get(["legend_blocked", "legend_done", "legend_normal", "sequence"])
        values = {
            **default_values,
            "name": status_name,
            "team_ids": [(6, 0, [helpdesk_team.id])],
        }
        return stage_model.create(values)

    def _get_or_create_helpdesk_tags(self, names: list[str]) -> list[tuple[int, int, list[int]]]:
        tag_model = self.env["helpdesk.tag"].sudo().with_context(IMPORT_CONTEXT)
        tag_ids: list[int] = []
        for name in names:
            if not name:
                continue
            tag = tag_model.search([("name", "=", name)], limit=1)
            if not tag:
                tag = tag_model.create({"name": name})
            tag_ids.append(tag.id)
        if not tag_ids:
            return []
        return [(6, 0, tag_ids)]

    @staticmethod
    def _compose_ticket_description(ticket: repairshopr_models.Ticket) -> str:
        lines: list[str] = []
        if ticket.problem_type:
            lines.append(f"Problem Type: {ticket.problem_type}")
        if ticket.status:
            lines.append(f"Status: {ticket.status}")
        if ticket.priority:
            lines.append(f"Priority: {ticket.priority}")
        if ticket.properties:
            for field_name, value in ticket.properties.__dict__.items():
                if field_name in {"id", "rs_client"}:
                    continue
                if value in (None, "", False):
                    continue
                label = field_name.replace("_", " ").title()
                lines.append(f"{label}: {value}")
        if ticket.comments:
            lines.append("")
            lines.append("Comments:")
            for comment in ticket.comments:
                if comment.hidden:
                    continue
                header_bits: list[str] = []
                if comment.created_at:
                    header_bits.append(str(comment.created_at))
                if comment.tech:
                    header_bits.append(f"Tech: {comment.tech}")
                header = " | ".join(header_bits) if header_bits else "Comment"
                subject = comment.subject or ""
                body = comment.body or ""
                if subject:
                    lines.append(f"- {header} — {subject}")
                else:
                    lines.append(f"- {header}")
                if body:
                    lines.append(body)
        return "\n".join(lines).strip()
