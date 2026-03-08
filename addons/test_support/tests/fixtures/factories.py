import random
import secrets
from datetime import datetime, timedelta

from odoo.api import Environment

from ..base_types import OdooValue
from ..test_helpers import generate_unique_name, generate_unique_sku


def _get_root_product_category(environment: Environment) -> "odoo.model.product_category":
    root_category = environment["product.category"].search([("parent_id", "=", False)], limit=1)
    if not root_category:
        root_category = environment["product.category"].create({"name": "All"})
    return root_category


def _ensure_product_variant(product_template: "odoo.model.product_template") -> "odoo.model.product_product":
    product_variant = product_template.env["product.product"].with_context(active_test=False).search(
        [("product_tmpl_id", "=", product_template.id)],
        limit=1,
    )
    if not product_variant:
        # Some template create paths defer variant materialization until explicitly requested.
        product_template._create_variant_ids()
        product_variant = product_template.env["product.product"].with_context(active_test=False).search(
            [("product_tmpl_id", "=", product_template.id)],
            limit=1,
        )
    return product_variant


class ProductFactory:
    @classmethod
    def create(cls, environment: Environment, **kwargs: OdooValue) -> "odoo.model.product_template":
        category_id = kwargs.get("categ_id") or _get_root_product_category(environment).id
        defaults = {
            "name": generate_unique_name("Test Product"),
            "default_code": generate_unique_sku(),
            "type": "consu",
            "list_price": 100.0,
            "standard_price": 50.0,
            "sale_ok": True,
            "purchase_ok": True,
            "categ_id": category_id,
            "uom_id": environment.ref("uom.product_uom_unit").id,
        }
        defaults.update(kwargs)
        product_template = environment["product.template"].with_context(skip_shopify_sync=True).create(defaults)
        _ensure_product_variant(product_template)
        return product_template

    @classmethod
    def create_batch(cls, environment: Environment, count: int = 5, **kwargs: OdooValue) -> "odoo.model.product_template":
        product_ids: list[int] = []
        for _ in range(count):
            product_ids.append(cls.create(environment, **kwargs).id)
        return environment["product.template"].with_context(skip_shopify_sync=True).browse(product_ids)

    @classmethod
    def create_with_variants(
        cls,
        environment: Environment,
        variant_count: int = 3,
        **kwargs: OdooValue,
    ) -> "odoo.model.product_template":
        product_template = cls.create(environment, **kwargs)

        color_attribute = environment["product.attribute"].create(
            {
                "name": "Test Color",
                "create_variant": "always",
            }
        )

        color_names = ["Red", "Blue", "Green", "Yellow", "Black"][:variant_count]
        color_values = []
        for color_name in color_names:
            color_values.append(
                environment["product.attribute.value"].create(
                    {
                        "name": color_name,
                        "attribute_id": color_attribute.id,
                    }
                )
            )

        environment["product.template.attribute.line"].create(
            {
                "product_tmpl_id": product_template.id,
                "attribute_id": color_attribute.id,
                "value_ids": [(6, 0, [color_value.id for color_value in color_values])],
            }
        )

        return product_template


class PartnerFactory:
    @classmethod
    def create(cls, environment: Environment, **kwargs: OdooValue) -> "odoo.model.res_partner":
        timestamp = datetime.now().timestamp()
        defaults = {
            "name": generate_unique_name("Test Partner"),
            "email": f"test_{timestamp}@example.com",
            "is_company": False,
            "customer_rank": 1,
            "supplier_rank": 0,
            "street": "123 Test Street",
            "city": "Test City",
            "zip": "12345",
            "country_id": environment.ref("base.us").id,
            "phone": f"+1{random.randint(2000000000, 9999999999)}",
        }
        defaults.update(kwargs)
        return environment["res.partner"].create(defaults)

    @classmethod
    def create_company(cls, environment: Environment, **kwargs: OdooValue) -> "odoo.model.res_partner":
        kwargs["is_company"] = True
        if "name" not in kwargs:
            kwargs["name"] = generate_unique_name("Test Company")
        return cls.create(environment, **kwargs)

    @classmethod
    def create_with_contacts(
        cls,
        environment: Environment,
        contact_count: int = 2,
        **kwargs: OdooValue,
    ) -> tuple["odoo.model.res_partner", "odoo.model.res_partner"]:
        company_partner = cls.create_company(environment, **kwargs)

        contact_partners = environment["res.partner"].browse()
        for contact_index in range(contact_count):
            contact_partner = cls.create(
                environment,
                parent_id=company_partner.id,
                name=f"Contact {contact_index + 1}",
                type="contact",
            )
            contact_partners |= contact_partner

        return company_partner, contact_partners


class SaleOrderFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.sale_order":
        partner = kwargs.get("partner_id")
        if not partner:
            partner = PartnerFactory.create(environment)
            kwargs["partner_id"] = partner.id
        elif isinstance(partner, int):
            kwargs["partner_id"] = partner
        elif hasattr(partner, "id"):
            kwargs["partner_id"] = getattr(partner, "id")
        else:
            raise TypeError(f"Unsupported partner_id type for SaleOrderFactory: {type(partner)!r}")

        defaults = {
            "partner_id": kwargs["partner_id"],
            "date_order": datetime.now(),
            "validity_date": datetime.now() + timedelta(days=30),
            "pricelist_id": environment["product.pricelist"].search([], limit=1).id,
            "payment_term_id": environment.ref("account.account_payment_term_immediate").id,
            "user_id": environment.user.id,
            "team_id": environment["crm.team"].search([], limit=1).id,
        }
        defaults.update(kwargs)

        order_lines = defaults.pop("order_line", [])
        sale_order = environment["sale.order"].create(defaults)

        if not order_lines:
            order_lines = SaleOrderFactory._create_default_lines(environment, sale_order)

        for order_line_values in order_lines:
            if isinstance(order_line_values, dict):
                order_line_values["order_id"] = sale_order.id
                environment["sale.order.line"].create(order_line_values)

        return sale_order

    @staticmethod
    def _create_default_lines(
        environment: Environment,
        sale_order: "odoo.model.sale_order",
    ) -> list["odoo.values.sale_order_line"]:
        products = ProductFactory.create_batch(environment, count=2)
        order_lines = []

        for product_template in products:
            order_lines.append(
                {
                    "order_id": sale_order.id,
                    "product_id": product_template.product_variant_id.id,
                    "product_uom_qty": random.randint(1, 10),
                    "price_unit": product_template.list_price,
                }
            )

        return order_lines


class DeliveryCarrierFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.delivery_carrier":
        defaults = {
            "name": kwargs.get("name", generate_unique_name("Test Carrier")),
            "delivery_type": kwargs.get("delivery_type", "fixed"),
            "product_id": kwargs.get("product_id") or environment.ref("delivery.product_product_delivery").id,
            "fixed_price": kwargs.get("fixed_price", 10.0),
        }
        defaults.update(kwargs)
        return environment["delivery.carrier"].create(defaults)


class ProductTagFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.product_tag":
        defaults = {
            "name": generate_unique_name("Test Tag"),
            "sequence": kwargs.get("sequence", 10),
            "color": kwargs.get("color", random.randint(1, 11)),
        }
        defaults.update(kwargs)
        return environment["product.tag"].create(defaults)


class CrmTagFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.crm_tag":
        defaults = {
            "name": generate_unique_name("Test CRM Tag"),
            "color": kwargs.get("color", random.randint(1, 11)),
        }
        defaults.update(kwargs)
        return environment["crm.tag"].create(defaults)


class SaleOrderLineFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.sale_order_line":
        order_id = kwargs.get("order_id")
        if not order_id:
            sale_order = SaleOrderFactory.create(environment)
            order_id = sale_order.id

        product_id = kwargs.get("product_id")
        if not product_id:
            product_template = ProductFactory.create(environment)
            product_id = product_template.product_variant_id.id

        defaults = {
            "order_id": order_id,
            "product_id": product_id,
            "product_uom_qty": kwargs.get("product_uom_qty", random.randint(1, 10)),
            "price_unit": kwargs.get("price_unit", 100.0),
        }
        defaults.update(kwargs)
        return environment["sale.order.line"].create(defaults)


class ProductAttributeFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.product_attribute":
        defaults = {
            "name": generate_unique_name("Test Attribute"),
            "create_variant": kwargs.get("create_variant", "always"),
            "display_type": kwargs.get("display_type", "radio"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return environment["product.attribute"].create(defaults)

    @staticmethod
    def create_with_values(
        environment: Environment,
        value_count: int = 3,
        **kwargs: OdooValue,
    ) -> tuple["odoo.model.product_attribute", "odoo.model.product_attribute_value"]:
        attribute = ProductAttributeFactory.create(environment, **kwargs)

        attribute_values = environment["product.attribute.value"].browse()
        for value_index in range(value_count):
            attribute_value = environment["product.attribute.value"].create(
                {
                    "name": f"Value {value_index + 1}",
                    "attribute_id": attribute.id,
                    "sequence": 10 + value_index,
                }
            )
            attribute_values |= attribute_value

        return attribute, attribute_values


class ResUsersFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.res_users":
        timestamp = datetime.now().timestamp()
        defaults = {
            "name": generate_unique_name("Test User"),
            "login": f"test_user_{timestamp}_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "email": f"test_{timestamp}@example.com",
            "group_ids": [(6, 0, [environment.ref("base.group_user").id])],
        }
        defaults.update(kwargs)
        return environment["res.users"].create(defaults)


class CurrencyFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.res_currency":
        defaults = {
            "name": kwargs.get("name", f"TST{random.randint(100, 999)}"),
            "symbol": kwargs.get("symbol", "$"),
            "rate": kwargs.get("rate", 1.0),
            "position": kwargs.get("position", "before"),
            "rounding": kwargs.get("rounding", 0.01),
        }
        defaults.update(kwargs)
        return environment["res.currency"].create(defaults)


class FiscalPositionFactory:
    @staticmethod
    def create(environment: Environment, **kwargs: OdooValue) -> "odoo.model.account_fiscal_position":
        defaults = {
            "name": generate_unique_name("Test Fiscal Position"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return environment["account.fiscal.position"].create(defaults)


__all__ = [
    "CrmTagFactory",
    "CurrencyFactory",
    "DeliveryCarrierFactory",
    "FiscalPositionFactory",
    "PartnerFactory",
    "ProductAttributeFactory",
    "ProductFactory",
    "ProductTagFactory",
    "ResUsersFactory",
    "SaleOrderFactory",
    "SaleOrderLineFactory",
]
