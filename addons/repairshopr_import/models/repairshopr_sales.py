import logging
from datetime import datetime
from typing import Any

from odoo import fields, models
from odoo.exceptions import UserError

from repairshopr_api import models as repairshopr_models
from repairshopr_api.client import Client

from .repairshopr_importer import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_ESTIMATE, RESOURCE_INVOICE

_logger = logging.getLogger(__name__)


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_estimates(self, repairshopr_client: Client, start_datetime: datetime | None) -> None:
        order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        estimates = repairshopr_client.get_model(repairshopr_models.Estimate, updated_at=start_datetime)
        for estimate in estimates:
            order_record = order_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(estimate.id),
                RESOURCE_ESTIMATE,
            )
            partner = self._get_or_create_partner_by_customer_id(
                estimate.customer_id,
                estimate.customer_business_then_name,
            )
            if not partner:
                _logger.warning("Skipping estimate %s because partner is missing", estimate.id)
                continue
            line_commands = self._build_sale_order_lines(repairshopr_client, estimate.id)
            values = self._build_sale_order_values(
                estimate,
                partner,
                line_commands,
                include_line_clear=bool(order_record),
            )
            if order_record:
                if order_record.state not in {"draft", "sent"}:
                    _logger.info("Skipping estimate %s because sale order is not editable", estimate.id)
                    continue
                order_record.write(values)
            else:
                order_record = order_model.create(values)
                order_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(estimate.id), RESOURCE_ESTIMATE)

    def _import_invoices(self, repairshopr_client: Client, start_datetime: datetime | None) -> None:
        move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
        sales_journal = self._get_sales_journal()
        invoices = repairshopr_client.get_model(repairshopr_models.Invoice, updated_at=start_datetime)
        for invoice in invoices:
            move_record = move_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(invoice.id),
                RESOURCE_INVOICE,
            )
            partner = self._get_or_create_partner_by_customer_id(
                invoice.customer_id,
                invoice.customer_business_then_name,
            )
            if not partner:
                _logger.warning("Skipping invoice %s because partner is missing", invoice.id)
                continue
            line_commands = self._build_invoice_lines(repairshopr_client, invoice.id)
            values = self._build_invoice_values(
                invoice,
                partner,
                line_commands,
                sales_journal,
                include_line_clear=bool(move_record),
            )
            if move_record:
                if move_record.state != "draft":
                    _logger.info("Skipping invoice %s because account move is not editable", invoice.id)
                    continue
                move_record.write(values)
            else:
                move_record = move_model.create(values)
                move_record.set_external_id(EXTERNAL_SYSTEM_CODE, str(invoice.id), RESOURCE_INVOICE)

    def _build_sale_order_values(
        self,
        estimate: repairshopr_models.Estimate,
        partner: "odoo.model.res_partner",
        line_commands: list[tuple],
        *,
        include_line_clear: bool,
    ) -> "odoo.values.sale_order":
        order_model = self.env["sale.order"].sudo().with_context(IMPORT_CONTEXT)
        default_values = order_model.default_get(["pricelist_id", "company_id", "team_id", "user_id"])
        order_lines = list(line_commands)
        if include_line_clear:
            order_lines = [(5, 0, 0)] + order_lines
        values: "odoo.values.sale_order" = {
            **default_values,
            "partner_id": partner.id,
            "client_order_ref": estimate.number or "",
            "date_order": estimate.date or estimate.created_at or fields.Datetime.now(),
            "order_line": order_lines,
        }
        if estimate.employee:
            values["note"] = estimate.employee
        return values

    def _build_invoice_values(
        self,
        invoice: repairshopr_models.Invoice,
        partner: "odoo.model.res_partner",
        line_commands: list[tuple],
        sales_journal: "odoo.model.account_journal",
        *,
        include_line_clear: bool,
    ) -> "odoo.values.account_move":
        move_model = self.env["account.move"].sudo().with_context(IMPORT_CONTEXT)
        default_values = move_model.default_get(["currency_id", "company_id"])
        invoice_lines = list(line_commands)
        if include_line_clear:
            invoice_lines = [(5, 0, 0)] + invoice_lines
        values: "odoo.values.account_move" = {
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
        if invoice.note:
            values["narration"] = invoice.note
        return values

    def _build_sale_order_lines(self, repairshopr_client: Client, estimate_id: int | None) -> list[tuple]:
        line_items = self._fetch_line_items(repairshopr_client, estimate_id=estimate_id)
        line_commands: list[tuple] = []
        for line_item_data in line_items:
            line_values = self._build_sale_order_line_values(line_item_data)
            if line_values:
                line_commands.append((0, 0, line_values))
        return line_commands

    def _build_invoice_lines(self, repairshopr_client: Client, invoice_id: int | None) -> list[tuple]:
        line_items = self._fetch_line_items(repairshopr_client, invoice_id=invoice_id)
        line_commands: list[tuple] = []
        for line_item_data in line_items:
            line_values = self._build_invoice_line_values(line_item_data)
            if line_values:
                line_commands.append((0, 0, line_values))
        return line_commands

    def _build_sale_order_line_values(self, line_item_data: dict[str, Any]) -> "odoo.values.sale_order_line":
        product_record = self._get_product_variant_for_line_item(
            line_item_data.get("product_id"),
            line_item_data.get("name") or line_item_data.get("item"),
        )
        quantity = self._to_float(line_item_data.get("quantity"), default=1.0)
        price = self._to_float(line_item_data.get("price"), default=0.0)
        discount = self._to_float(line_item_data.get("discount_percent"), default=0.0)
        name = line_item_data.get("name") or line_item_data.get("item") or product_record.display_name
        values: "odoo.values.sale_order_line" = {
            "product_id": product_record.id,
            "name": name,
            "product_uom_qty": quantity,
            "price_unit": price,
        }
        if discount:
            values["discount"] = discount
        return values

    def _build_invoice_line_values(self, line_item_data: dict[str, Any]) -> "odoo.values.account_move_line":
        product_record = self._get_product_variant_for_line_item(
            line_item_data.get("product_id"),
            line_item_data.get("name") or line_item_data.get("item"),
        )
        quantity = self._to_float(line_item_data.get("quantity"), default=1.0)
        price = self._to_float(line_item_data.get("price"), default=0.0)
        name = line_item_data.get("name") or line_item_data.get("item") or product_record.display_name
        values: "odoo.values.account_move_line" = {
            "product_id": product_record.id,
            "name": name,
            "quantity": quantity,
            "price_unit": price,
        }
        return values

    @staticmethod
    def _fetch_line_items(
        repairshopr_client: Client,
        *,
        estimate_id: int | None = None,
        invoice_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query_parameters: dict[str, str] = {}
        if estimate_id:
            query_parameters["estimate_id"] = str(estimate_id)
        if invoice_id:
            query_parameters["invoice_id"] = str(invoice_id)
        if not query_parameters:
            return []
        line_items = repairshopr_client.fetch_from_api("line_item", params=query_parameters)[0]
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
