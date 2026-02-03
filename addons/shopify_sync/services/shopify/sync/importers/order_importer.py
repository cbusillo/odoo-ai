import logging
import re
from datetime import datetime
from decimal import Decimal

from odoo import Command
from odoo.api import Environment
from pydantic import BaseModel, field_validator

from ...gql import (
    AddressFields,
    Client,
    CurrencyCode,
    MoneyBagFields,
    OrderFields,
    OrderLineItemFields,
)
from ...helpers import (
    ShopifyDataError,
    find_partner_by_shopify_address_id,
    find_record_by_external_id,
    map_records_by_external_ids,
    parse_shopify_id_from_gid,
    parse_shopify_sku_field_to_sku_and_bin,
    write_if_changed,
)
from ..base import ShopifyBaseImporter, ShopifyPage
from .customer_importer import AddressRole, CustomerImporter

_logger = logging.getLogger(__name__)


class EbayOrderData(BaseModel):
    sales_record: str | None = None
    order_id: str | None = None
    latest_delivery_date: datetime | None = None
    earliest_delivery_date: datetime | None = None

    @field_validator("latest_delivery_date", "earliest_delivery_date", mode="before")
    @classmethod
    def parse_datetime(cls, value: str | datetime | None) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        try:
            from ...helpers import parse_shopify_datetime_to_utc

            return parse_shopify_datetime_to_utc(value)
        except (ValueError, TypeError):
            return None

    @classmethod
    def from_note_attributes(cls, note_attributes: str) -> "EbayOrderData":
        parsed_fields = {}

        sales_record_match = re.search(r"eBay Sales Record Number:\s*(\S+)", note_attributes)
        if sales_record_match:
            parsed_fields["sales_record"] = sales_record_match.group(1)

        order_id_match = re.search(r"eBay Order Id:\s*(\S+)", note_attributes)
        if order_id_match:
            parsed_fields["order_id"] = order_id_match.group(1)

        latest_delivery_match = re.search(r"eBay Latest Delivery Date:\s*(\S+)", note_attributes)
        if latest_delivery_match:
            parsed_fields["latest_delivery_date"] = latest_delivery_match.group(1)

        earliest_delivery_match = re.search(r"eBay Earliest Delivery Date:\s*(\S+)", note_attributes)
        if earliest_delivery_match:
            parsed_fields["earliest_delivery_date"] = earliest_delivery_match.group(1)

        return cls(**parsed_fields)


class OrderImporter(ShopifyBaseImporter[OrderFields]):
    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        super().__init__(env, sync_record)

    @staticmethod
    def _get_amount_for_order_currency(price_set: MoneyBagFields, order_currency: CurrencyCode) -> Decimal:
        if not price_set:
            return Decimal("0.0")
        if (
            price_set.shop_money
            and price_set.shop_money.currency_code
            and price_set.shop_money.currency_code == order_currency
            and price_set.shop_money.amount > 0
        ):
            return price_set.shop_money.amount
        if price_set.presentment_money:
            return price_set.presentment_money.amount
        return Decimal("0.0")

    @staticmethod
    def _get_discount_allocation_amount(line: OrderLineItemFields, order_currency: CurrencyCode) -> Decimal:
        return sum(
            (
                OrderImporter._get_amount_for_order_currency(allocation.allocated_amount_set, order_currency)
                for allocation in line.discount_allocations
                if allocation and allocation.allocated_amount_set
            ),
            Decimal("0.0"),
        )

    def _fetch_page(self, client: Client, query: str | None, cursor: str | None) -> ShopifyPage[OrderFields]:
        return client.get_orders(query=query, cursor=cursor, limit=self.page_size)

    def import_orders_since_last_import(self) -> int:
        return self.run_since_last_import("order")

    def _import_one(self, shopify_order: OrderFields) -> bool:
        if not shopify_order.customer:
            _logger.warning(f"Order {shopify_order.name} has no customer; skipping order")
            return False
        CustomerImporter(self.env, self.sync_record).import_customer(shopify_order.customer)

        shopify_customer_id = parse_shopify_id_from_gid(shopify_order.customer.id)
        partner = self.env["res.partner"].browse(
            find_record_by_external_id(
                self.env,
                model_name="res.partner",
                system_code="shopify",
                resource="customer",
                external_id_value=shopify_customer_id,
            ).id
        )

        if not partner:
            _logger.warning(f"Customer {shopify_customer_id} not found for order {shopify_order.name}; skipping order")
            return False

        if shopify_order.shipping_address:
            shipping_partner = self._resolve_address(shopify_order.shipping_address, partner, role="shipping")
        else:
            shipping_partner = partner

        if shopify_order.billing_address:
            billing_partner = self._resolve_address(shopify_order.billing_address, partner, role="billing")
        else:
            billing_partner = partner

        currency = self.env["res.currency"].search([("name", "=", shopify_order.currency_code.value)], limit=1)
        if not currency:
            raise ShopifyDataError(f"Unsupported currency {shopify_order.currency_code.value}")

        shopify_order_id = parse_shopify_id_from_gid(shopify_order.id)
        existing_order = (
            self.env["sale.order"]
            .with_context(skip_shopify_sync=True)
            .search([("shopify_order_id", "=", shopify_order_id)], limit=1)
        )

        order_values: "odoo.values.sale_order" = {
            "shopify_order_id": shopify_order_id,
            "name": shopify_order.name,
            "date_order": shopify_order.created_at,
            "partner_id": partner.id,
            "partner_invoice_id": billing_partner.id,
            "partner_shipping_id": shipping_partner.id,
            "currency_id": currency.id,
            "source_platform": "shopify",
            "state": "sale",
            "locked": True,
            "invoice_status": "invoiced",
        }

        note_parts = []

        if shopify_order.payment_gateway_names:
            payment_methods = ", ".join(shopify_order.payment_gateway_names)
            note_parts.append(f"Payment: {payment_methods}")

        if shopify_order.note:
            note_parts.append(shopify_order.note)

        note_attributes = None
        if shopify_order.custom_attributes:
            for attr in shopify_order.custom_attributes:
                if attr.key == "Note Attributes" and attr.value:
                    note_attributes = attr.value
                    break

        if note_attributes:
            ebay_data = EbayOrderData.from_note_attributes(note_attributes)
            if ebay_data.latest_delivery_date:
                order_values["commitment_date"] = ebay_data.latest_delivery_date
            if ebay_data.sales_record or ebay_data.order_id:
                order_values["source_platform"] = "ebay"
                if ebay_data.sales_record:
                    note_parts.append(f"eBay Sales Record: {ebay_data.sales_record}")
                if ebay_data.order_id:
                    note_parts.append(f"eBay Order ID: {ebay_data.order_id}")

        if note_parts:
            order_values["shopify_note"] = "\n".join(note_parts)

        if existing_order:
            # Don't change lock status of existing orders
            update_values = order_values.copy()
            update_values.pop("locked", None)
            update_values.pop("state", None)  # Don't change state either
            update_values.pop("invoice_status", None)  # Don't change invoice status

            changed = write_if_changed(existing_order, update_values)
            changed |= self._sync_order_lines(existing_order, shopify_order)

            return changed
        new_order = self.env["sale.order"].with_context(skip_shopify_sync=True, skip_procurement=True).create(order_values)
        self._sync_order_lines(new_order, shopify_order)

        return True

    def _sync_order_lines(self, odoo_order: "odoo.model.sale_order", shopify_order: OrderFields) -> bool:
        changed = False
        line_items = shopify_order.line_items.nodes

        # Temporarily unlock the order if it's locked to allow line updates
        was_locked = odoo_order.locked
        if was_locked:
            odoo_order.with_context(skip_shopify_sync=True, skip_procurement=True).write({"locked": False})

        existing_by_line_id: dict[str, "odoo.model.sale_order_line"] = {
            line.shopify_order_line_id: line for line in odoo_order.order_line
        }
        processed_keys: set[str] = set()

        # bulk product pre‑fetch
        sku_list: list[str] = []
        variant_external_ids: list[str] = []
        for line in line_items:
            try:
                sku, _ = parse_shopify_sku_field_to_sku_and_bin(line.sku or "")
            except ShopifyDataError:
                continue
            sku_list.append(sku)
            variant_external_ids.append(parse_shopify_id_from_gid(line.variant.id))

        product_by_sku: dict[str, "odoo.model.product_product"] = {}
        if sku_list:
            products = self.env["product.product"].search([("default_code", "in", sku_list)])
            product_by_sku = {product.default_code: product for product in products if product.default_code}

        raw_product_by_variant = map_records_by_external_ids(
            self.env,
            model_name="product.product",
            system_code="shopify",
            resource="variant",
            external_ids=variant_external_ids,
        )
        product_model: "odoo.model.product_product" = self.env["product.product"]
        product_by_variant: dict[str, "odoo.model.product_product"] = {}
        for external_id_value, product in raw_product_by_variant.items():
            if product and product.exists():
                product_by_variant[external_id_value] = product_model.browse(product.id)

        for shopify_line in line_items:
            shopify_line_item_id = parse_shopify_id_from_gid(shopify_line.id)
            processed_keys.add(shopify_line_item_id)

            try:
                sku, _ = parse_shopify_sku_field_to_sku_and_bin(shopify_line.sku or "")
            except ShopifyDataError:
                _logger.warning(f"Missing SKU for Shopify line {shopify_line.id} in order {shopify_order.name}")
                continue

            variant_external_id = parse_shopify_id_from_gid(shopify_line.variant.id)
            product = product_by_sku.get(sku) or product_by_variant.get(variant_external_id)
            if not product:
                _logger.warning(f"No matching product for SKU {sku} in order {shopify_order.name}")
                continue

            if shopify_line.quantity <= 0:
                raise ShopifyDataError(f"Invalid quantity {shopify_line.quantity} for line {shopify_line.id}")

            price_set = shopify_line.original_unit_price_set
            discount_amount_dec = self._get_discount_allocation_amount(shopify_line, shopify_order.currency_code)
            if not price_set or not price_set.presentment_money:
                _logger.warning(f"Missing price for line {shopify_line.id} in order {shopify_order.name}; skipping line")
                continue
            price_unit_dec = self._get_amount_for_order_currency(price_set, shopify_order.currency_code)
            if discount_amount_dec and shopify_line.quantity:
                price_unit_dec -= discount_amount_dec / shopify_line.quantity
            price_unit_val = float(price_unit_dec)
            line_vals: "odoo.values.sale_order_line" = {
                "order_id": odoo_order.id,
                "product_id": product.id,
                "product_uom_qty": shopify_line.quantity,
                "price_unit": price_unit_val,
                "name": shopify_line.name,
                "shopify_order_line_id": shopify_line_item_id,
            }
            existing_line = existing_by_line_id.pop(shopify_line_item_id, None)
            if existing_line:
                changed |= write_if_changed(existing_line, line_vals)
            else:
                self.env["sale.order.line"].with_context(skip_shopify_sync=True, skip_procurement=True).create(line_vals)
                changed = True

        shipping_changed = self._apply_shipping(odoo_order, shopify_order)
        discount_changed = self._apply_global_discount(odoo_order, shopify_order)
        tracking_changed = self._apply_tracking(odoo_order, shopify_order)
        changed |= shipping_changed or discount_changed or tracking_changed

        for tax_line in shopify_order.tax_lines:
            if not tax_line or not tax_line.price_set:
                continue
            tax_amount_dec = self._get_amount_for_order_currency(tax_line.price_set, shopify_order.currency_code)
            if tax_amount_dec == 0:
                continue
            tax_product = self._get_special_product("TAX", tax_line.title or "Tax")
            tax_key = f"tax:{parse_shopify_id_from_gid(shopify_order.id)}:{tax_line.title or tax_line.rate_percentage}"
            processed_keys.add(tax_key)
            tax_vals: "odoo.values.sale_order_line" = {
                "order_id": odoo_order.id,
                "product_id": tax_product.id,
                "product_uom_qty": 1,
                "price_unit": float(tax_amount_dec),
                "name": tax_line.title or "Tax",
                "shopify_order_line_id": tax_key,
            }
            existing_tax = existing_by_line_id.pop(tax_key, None)
            if existing_tax:
                changed |= write_if_changed(existing_tax, tax_vals)
            else:
                self.env["sale.order.line"].with_context(skip_shopify_sync=True, skip_procurement=True).create(tax_vals)
                changed = True

        current_by_line_id = {line.shopify_order_line_id: line for line in odoo_order.order_line if line.shopify_order_line_id}
        stale_ids = [line.id for key, line in current_by_line_id.items() if key not in processed_keys]
        if stale_ids:
            self.env["sale.order.line"].browse(stale_ids).unlink()
            changed = True

        # Re-lock the order if it was locked before
        if was_locked:
            # Re-lock and ensure invoice status is set for imported orders
            write_vals = {"locked": True}
            if not existing_by_line_id:  # New order (no existing lines)
                write_vals["invoice_status"] = "invoiced"
            odoo_order.with_context(skip_shopify_sync=True).write(write_vals)

        return changed

    def _apply_shipping(self, odoo_order: "odoo.model.sale_order", shopify_order: OrderFields) -> bool:
        shipping_lines = [line for line in shopify_order.shipping_lines.nodes if line and line.is_removed is not True]

        grouped: dict[str, list] = {}
        service_map_model = self.env["delivery.carrier.service.map"]
        for line in shipping_lines:
            normalized_name = service_map_model.normalize_service_name(line.title or "")
            grouped.setdefault(normalized_name, []).append(line)

        existing_delivery_lines = odoo_order.order_line.filtered("is_delivery")
        existing_by_product_id = {line.product_id.id: line for line in existing_delivery_lines}
        processed_product_ids: set[int] = set()

        first_group = True
        changed = False
        total_shipping_charge = 0.0

        for normalised_name, lines in grouped.items():
            total_amount = sum(
                self._get_amount_for_order_currency(
                    (l.discounted_price_set or l.current_discounted_price_set or l.original_price_set),
                    shopify_order.currency_code,
                )
                for l in lines
            )
            total_shipping_charge += float(total_amount)

            mapping = self.env["delivery.carrier.service.map"].search(
                [("platform", "=", "shopify"), ("platform_service_normalized_name", "=", normalised_name)],
                limit=1,
            )
            if not mapping:
                service_name = lines[0].title or "Unknown"

                shop_url_key = self.env["ir.config_parameter"].sudo().get_param("shopify.shop_url_key", "")
                shopify_order_id = parse_shopify_id_from_gid(shopify_order.id)
                order_url = f"https://{shop_url_key}/admin/orders/{shopify_order_id}" if shop_url_key else ""

                base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
                mapping_url = f"{base_url}/odoo#action=&model=delivery.carrier.service.map&view_type=list" if base_url else ""

                error_msg = (
                    f"Unknown delivery service '{service_name}' in order {shopify_order.name}. "
                    f"Order: {order_url} | "
                    f"Add mapping for '{normalised_name}' here: {mapping_url}"
                )
                raise ShopifyDataError(error_msg, shopify_record=shopify_order)

            carrier = mapping.carrier
            delivery_product = carrier.product_id
            product_id = delivery_product.id
            processed_product_ids.add(product_id)

            # Only create delivery line if there's a charge
            if total_amount > 0:
                line_values: "odoo.values.sale_order_line" = {
                    "product_id": product_id,
                    "product_uom_qty": 1,
                    "price_unit": float(total_amount),
                    "name": lines[0].title or carrier.name,
                    "is_delivery": True,
                }

                existing_line = existing_by_product_id.get(product_id)
                if existing_line:
                    changed |= write_if_changed(existing_line, line_values)
                else:
                    self.env["sale.order.line"].with_context(skip_shopify_sync=True, skip_procurement=True).create(
                        {"order_id": odoo_order.id, **line_values}
                    )
                    changed = True

            if first_group:
                if odoo_order.carrier_id.id != carrier.id:
                    odoo_order.carrier_id = carrier.id
                    changed = True
                first_group = False

        stale_lines = existing_delivery_lines.filtered(lambda line: line.product_id.id not in processed_product_ids)
        if stale_lines:
            stale_lines.unlink()
            changed = True

        if odoo_order.shipping_charge != total_shipping_charge:
            odoo_order.shipping_charge = total_shipping_charge
            changed = True

        return changed

    def _apply_global_discount(self, odoo_order: "odoo.model.sale_order", shopify_order: OrderFields) -> bool:
        discount_reason = "Discount"
        if shopify_order.discount_applications and shopify_order.discount_applications.nodes:
            parts: list[str] = []
            for app in shopify_order.discount_applications.nodes:
                title_or_code = getattr(app, "title", "") or getattr(app, "code", "")
                if title_or_code:
                    parts.append(title_or_code.strip())
            if parts:
                discount_reason = ", ".join(dict.fromkeys(parts))

        discount_amount = self._get_amount_for_order_currency(shopify_order.total_discounts_set, shopify_order.currency_code)

        # locate any existing discount line by matching the discount product
        discount_product = self.env["product.product"].search([("default_code", "=", "DISC")], limit=1)
        if not discount_product:
            discount_product = self._get_special_product("DISC", "Discount")
        discount_lines = odoo_order.order_line.filtered(lambda l: l.product_id.id == discount_product.id)

        if discount_amount == 0:
            if discount_lines:
                discount_lines.unlink()
                return True
            return False

        discount_vals: "odoo.values.sale_order_line" = {
            "order_id": odoo_order.id,
            "product_id": discount_product.id,
            "product_uom_qty": 1,
            "price_unit": -float(discount_amount),
            "name": discount_reason,
        }

        # Propagate tax from a product line with tax, if present
        product_line_with_tax = odoo_order.order_line.filtered(lambda line: line.tax_ids)[:1]
        if product_line_with_tax:
            # ORM write format differs from type's read format for M2M fields
            discount_vals["tax_ids"] = [Command.set(product_line_with_tax.tax_ids.ids)]  # type: ignore[assignment]

        if discount_lines:
            return write_if_changed(discount_lines[0], discount_vals)

        self.env["sale.order.line"].with_context(skip_shopify_sync=True).create(discount_vals)
        return True

    def _apply_tracking(self, odoo_order: "odoo.model.sale_order", shopify_order: OrderFields) -> bool:
        numbers = self._extract_tracking_numbers(shopify_order)
        if not numbers:
            return False
        tracking_ref = ", ".join(numbers)
        picking = odoo_order.picking_ids.sorted("id", reverse=True)[:1]
        if not picking:
            return False
        if picking.carrier_tracking_ref != tracking_ref:
            picking.carrier_tracking_ref = tracking_ref
            return True
        return False

    @staticmethod
    def _extract_tracking_numbers(shopify_order: OrderFields) -> list[str]:
        numbers: list[str] = []
        if shopify_order.fulfillments:
            for fulfillment in shopify_order.fulfillments:
                if fulfillment and fulfillment.tracking_info:
                    for info in fulfillment.tracking_info:
                        if info and info.number:
                            numbers.append(info.number.strip())
        return list(dict.fromkeys(filter(None, numbers)))

    def _get_special_product(self, default_code: str, name: str) -> "odoo.model.product_product":
        product = self.env["product.product"].search([("default_code", "=", default_code)], limit=1)
        if product:
            return product
        return (
            self.env["product.product"]
            .with_context(skip_sku_check=True)
            .create(
                {
                    "name": name,
                    "default_code": default_code,
                    "type": "consu",
                    "sale_ok": True,
                    "purchase_ok": False,
                    "invoice_policy": "order",
                }
            )
        )

    def _resolve_address(
        self, shopify_address: AddressFields, partner: "odoo.model.res_partner", role: AddressRole
    ) -> "odoo.model.res_partner":
        if not shopify_address:
            return partner

        shopify_address_id = parse_shopify_id_from_gid(shopify_address.id)
        address_partner = find_partner_by_shopify_address_id(self.env, shopify_address_id, role=role)
        if address_partner:
            return address_partner

        CustomerImporter(self.env, self.sync_record).process_address(shopify_address, partner, role=role)
        return find_partner_by_shopify_address_id(self.env, shopify_address_id, role=role) or partner
