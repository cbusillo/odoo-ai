from datetime import datetime

from odoo import models

from repairshopr_api import models as repairshopr_models
from repairshopr_api.client import Client

from .repairshopr_importer import DEFAULT_HELPDESK_TEAM_NAME, EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_TICKET


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_tickets(self, repairshopr_client: Client, start_datetime: datetime | None) -> None:
        ticket_model = self.env["helpdesk.ticket"].sudo().with_context(IMPORT_CONTEXT)
        helpdesk_team = self._get_helpdesk_team()
        tickets = repairshopr_client.get_model(repairshopr_models.Ticket, updated_at=start_datetime)
        for ticket in tickets:
            ticket_record = ticket_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(ticket.id),
                RESOURCE_TICKET,
            )
            partner = self._get_or_create_partner_by_customer_id(
                ticket.customer_id,
                ticket.customer_business_then_name,
            )
            values = self._build_ticket_values(ticket, partner, helpdesk_team)
            if ticket_record:
                ticket_record.write(values)
            else:
                ticket_record = ticket_model.create(values)
                ticket_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(ticket.id), RESOURCE_TICKET)

    def _build_ticket_values(
        self,
        ticket: repairshopr_models.Ticket,
        partner: "odoo.model.res_partner",
        helpdesk_team: "odoo.model.helpdesk_team",
    ) -> "odoo.values.helpdesk_ticket":
        name = ticket.subject or f"RepairShopr Ticket {ticket.number or ticket.id}"
        values: "odoo.values.helpdesk_ticket" = {
            "name": name,
            "team_id": helpdesk_team.id,
            "description": self._compose_ticket_description(ticket),
        }
        if partner:
            values["partner_id"] = partner.id
        if ticket.status:
            stage = self._get_helpdesk_stage(helpdesk_team, ticket.status)
            values["stage_id"] = stage.id
        if "priority" in self.env["helpdesk.ticket"]._fields and ticket.priority:
            values["priority"] = ticket.priority
        if "tag_ids" in self.env["helpdesk.ticket"]._fields and ticket.problem_type:
            values["tag_ids"] = self._get_or_create_helpdesk_tags([ticket.problem_type])
        return values

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
