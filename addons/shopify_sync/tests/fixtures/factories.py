import random
from datetime import datetime, timedelta

from odoo.api import Environment
from odoo.models import Model

from ..base_types import OdooValue
from ..test_helpers import (
    generate_motor_serial,
    generate_shopify_id,
    generate_unique_name,
    generate_unique_sku,
)


class ProductFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_template":
        shopify_product_id = kwargs.pop("shopify_product_id", None)
        shopify_variant_id = kwargs.pop("shopify_variant_id", None)
        shopify_condition_id = kwargs.pop("shopify_condition_id", None)
        shopify_ebay_category_id = kwargs.pop("shopify_ebay_category_id", None)
        category_id = kwargs.get("categ_id")
        if not category_id:
            root_category = env["product.category"].search([("parent_id", "=", False)], limit=1)
            if not root_category:
                root_category = env["product.category"].create({"name": "All"})
            category_id = root_category.id
        defaults = {
            "name": generate_unique_name("Test Product"),
            "default_code": generate_unique_sku(),
            "type": "consu",
            "list_price": 100.0,
            "standard_price": 50.0,
            "sale_ok": True,
            "purchase_ok": True,
            "categ_id": category_id,
            "uom_id": env.ref("uom.product_uom_unit").id,
            "invoice_policy": "order",
            "website_description": "Test product description",
        }
        defaults.update(kwargs)
        if "source" not in env["product.template"]._fields:
            defaults.pop("source", None)
        elif "source" not in defaults:
            defaults["source"] = "standard"
        product = env["product.template"].with_context(skip_shopify_sync=True).create(defaults)
        product_variant = product.with_context(active_test=False).product_variant_id
        if shopify_product_id:
            product_variant.set_external_id("shopify", str(shopify_product_id), resource="product")
        if shopify_variant_id:
            product_variant.set_external_id("shopify", str(shopify_variant_id), resource="variant")
        if shopify_condition_id:
            product_variant.set_external_id("shopify", str(shopify_condition_id), resource="condition")
        if shopify_ebay_category_id:
            product_variant.set_external_id("shopify", str(shopify_ebay_category_id), resource="ebay_category")
        return product

    @staticmethod
    def create_batch(env: Environment, count: int = 5, **kwargs: OdooValue) -> "odoo.model.product_template":
        product_ids: list[int] = []
        for _ in range(count):
            product_ids.append(ProductFactory.create(env, **kwargs).id)
        return env["product.template"].with_context(skip_shopify_sync=True).browse(product_ids)

    @staticmethod
    def create_with_variants(env: Environment, variant_count: int = 3, **kwargs: OdooValue) -> "odoo.model.product_template":
        product = ProductFactory.create(env, **kwargs)

        color_attr = env["product.attribute"].create(
            {
                "name": "Test Color",
                "create_variant": "always",
            }
        )

        colors = ["Red", "Blue", "Green", "Yellow", "Black"][:variant_count]
        color_values = []
        for color in colors:
            color_values.append(
                env["product.attribute.value"].create(
                    {
                        "name": color,
                        "attribute_id": color_attr.id,
                    }
                )
            )

        env["product.template.attribute.line"].create(
            {
                "product_tmpl_id": product.id,
                "attribute_id": color_attr.id,
                "value_ids": [(6, 0, [v.id for v in color_values])],
            }
        )

        return product


class PartnerFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.res_partner":
        timestamp = datetime.now().timestamp()
        shopify_customer_id = kwargs.pop("shopify_customer_id", None)
        shopify_address_id = kwargs.pop("shopify_address_id", None)
        ebay_username = kwargs.pop("ebay_username", None)
        defaults = {
            "name": generate_unique_name("Test Partner"),
            "email": f"test_{timestamp}@example.com",
            "is_company": False,
            "customer_rank": 1,
            "supplier_rank": 0,
            "street": "123 Test Street",
            "city": "Test City",
            "zip": "12345",
            "country_id": env.ref("base.us").id,
            "phone": f"+1{random.randint(2000000000, 9999999999)}",
        }
        defaults.update(kwargs)
        partner = env["res.partner"].create(defaults)
        if shopify_customer_id:
            partner.set_external_id("shopify", str(shopify_customer_id), resource="customer")
        if shopify_address_id:
            partner.set_external_id("shopify", str(shopify_address_id), resource="address_invoice")
        if ebay_username:
            partner.set_external_id("ebay", str(ebay_username), resource="profile")
        return partner

    @staticmethod
    def create_company(env: Environment, **kwargs: OdooValue) -> "odoo.model.res_partner":
        kwargs["is_company"] = True
        if "name" not in kwargs:
            kwargs["name"] = generate_unique_name("Test Company")
        return PartnerFactory.create(env, **kwargs)

    @staticmethod
    def create_with_contacts(
        env: Environment, contact_count: int = 2, **kwargs: OdooValue
    ) -> tuple["odoo.model.res_partner", "odoo.model.res_partner"]:
        company = PartnerFactory.create_company(env, **kwargs)

        contacts = env["res.partner"].browse()
        for i in range(contact_count):
            contact = PartnerFactory.create(
                env,
                parent_id=company.id,
                name=f"Contact {i + 1}",
                type="contact",
            )
            contacts |= contact

        return company, contacts


class MotorFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_template":
        manufacturer = env["product.manufacturer"].search([("is_motor_manufacturer", "=", True)], limit=1)
        if not manufacturer:
            manufacturer = env["product.manufacturer"].create({"name": "Test Motor Manufacturer", "is_motor_manufacturer": True})

        stroke = env["motor.stroke"].search([], limit=1)
        if not stroke:
            stroke = env["motor.stroke"].sudo().create({"name": "4-Stroke", "code": "4"})

        configuration = env["motor.configuration"].search([], limit=1)
        if not configuration:
            configuration = env["motor.configuration"].sudo().create({"name": "V6", "code": "V6"})

        motor_field_mapping = {
            "motor_hp": "horsepower",
            "motor_year": "year",
            "motor_model": "model",
            "motor_serial": "serial_number",
            "location": "location",
            "cost": "cost",
        }

        motor_kwargs = {}
        product_kwargs = {}
        for key, value in kwargs.items():
            if key in motor_field_mapping:
                motor_kwargs[motor_field_mapping[key]] = value
            else:
                product_kwargs[key] = value

        motor_vals = {
            "horsepower": motor_kwargs.get("horsepower", random.choice([25, 40, 60, 75, 90, 115, 150])),
            "year": motor_kwargs.get("year", random.randint(2015, 2024)),
            "model": motor_kwargs.get("model", f"Model-{random.choice(['X', 'Y', 'Z'])}{random.randint(100, 999)}"),
            "serial_number": motor_kwargs.get("serial_number", generate_motor_serial()),
            "motor_number": generate_unique_sku(),
            "manufacturer": manufacturer.id,
            "stroke": stroke.id,
            "configuration": configuration.id,
        }

        if "location" in motor_kwargs:
            motor_vals["location"] = motor_kwargs["location"]
        if "cost" in motor_kwargs:
            motor_vals["cost"] = motor_kwargs["cost"]

        motor = env["motor"].create(motor_vals)

        category_id = product_kwargs.get("categ_id")
        if not category_id:
            root_category = env["product.category"].search([("parent_id", "=", False)], limit=1)
            if not root_category:
                root_category = env["product.category"].create({"name": "All"})
            category_id = root_category.id

        defaults = {
            "name": product_kwargs.get("name") or generate_unique_name("Test Motor"),
            "default_code": motor_vals["motor_number"],
            "type": "consu",
            "list_price": 2500.0,
            "standard_price": 1500.0,
            "weight": 150.0,
            "volume": 0.5,
            "categ_id": category_id,
            "motor": motor.id,
        }
        for key, value in product_kwargs.items():
            if key != "name":
                defaults[key] = value

        if "source" not in env["product.template"]._fields:
            defaults.pop("source", None)
        elif "source" not in defaults:
            defaults["source"] = "motor"

        return env["product.template"].with_context(skip_shopify_sync=True).create(defaults)


class MotorProductTemplateFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.motor_product_template":
        part_type = kwargs.get("part_type")
        if not part_type:
            part_type = env["product.type"].create({"name": generate_unique_name("Test Part Type")})
            kwargs["part_type"] = part_type.id
        elif isinstance(part_type, Model):
            kwargs["part_type"] = part_type.id

        defaults = {
            "name": generate_unique_name("Test Motor Template"),
            "initial_quantity": 1.0,
            "bin": f"BIN-{random.randint(100, 999)}",
            "weight": random.uniform(1.0, 50.0),
            "include_year_in_name": True,
            "include_hp_in_name": True,
            "include_model_in_name": False,
            "include_oem_in_name": False,
            "is_quantity_listing": False,
            "year_from": random.randint(1990, 2015) if random.choice([True, False]) else None,
            "year_to": random.randint(2016, 2024) if random.choice([True, False]) else None,
        }
        defaults.update(kwargs)

        if defaults.get("year_from") and defaults.get("year_to"):
            if defaults["year_from"] > defaults["year_to"]:
                defaults["year_from"], defaults["year_to"] = defaults["year_to"], defaults["year_from"]

        return env["motor.product.template"].create(defaults)

    @staticmethod
    def create_with_filters(env: Environment, **kwargs: OdooValue) -> "odoo.model.motor_product_template":
        stroke = env["motor.stroke"].search([], limit=1)
        if not stroke:
            stroke = env["motor.stroke"].sudo().create({"name": "2-Stroke", "code": "2"})

        config = env["motor.configuration"].search([], limit=1)
        if not config:
            config = env["motor.configuration"].sudo().create({"name": "Inline-4", "code": "I4"})

        manufacturer = env["product.manufacturer"].search([("is_motor_manufacturer", "=", True)], limit=1)
        if not manufacturer:
            manufacturer = env["product.manufacturer"].create({"name": "Filter Test Manufacturer", "is_motor_manufacturer": True})

        defaults = {
            "strokes": [(6, 0, [stroke.id])],
            "configurations": [(6, 0, [config.id])],
            "manufacturers": [(6, 0, [manufacturer.id])],
        }
        defaults.update(kwargs)

        return MotorProductTemplateFactory.create(env, **defaults)


class ShopifyProductFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_template":
        defaults = {
            "shopify_sync": True,
            "shopify_inventory_item_id": generate_shopify_id(),
            "shopify_handle": f"test-product-{random.randint(1000, 9999)}",
            "shopify_tags": "test,automated",
            "shopify_vendor": "Test Vendor",
            "shopify_product_type": "Test Type",
            "shopify_last_sync": datetime.now(),
        }
        external_id_keys = {
            "shopify_product_id",
            "shopify_variant_id",
            "shopify_condition_id",
            "shopify_ebay_category_id",
        }

        product_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("shopify_")}
        product = ProductFactory.create(env, **product_kwargs)

        shopify_fields = {
            k: v for k, v in defaults.items() if k.startswith("shopify_") and k not in external_id_keys
        }
        shopify_fields.update(
            {
                k: v
                for k, v in kwargs.items()
                if k.startswith("shopify_") and k not in external_id_keys
            }
        )

        product.write(shopify_fields)
        product_variant = product.product_variant_id
        shopify_product_id = str(kwargs.get("shopify_product_id") or generate_shopify_id())
        shopify_variant_id = str(kwargs.get("shopify_variant_id") or generate_shopify_id())
        product_variant.set_external_id("shopify", shopify_product_id, resource="product")
        product_variant.set_external_id("shopify", shopify_variant_id, resource="variant")

        if "shopify_condition_id" in kwargs:
            product_variant.set_external_id(
                "shopify",
                str(kwargs["shopify_condition_id"]),
                resource="condition",
            )
        if "shopify_ebay_category_id" in kwargs:
            product_variant.set_external_id(
                "shopify",
                str(kwargs["shopify_ebay_category_id"]),
                resource="ebay_category",
            )
        return product


class SaleOrderFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.sale_order":
        partner = kwargs.get("partner_id")
        if not partner:
            partner = PartnerFactory.create(env)
            kwargs["partner_id"] = partner.id
        elif isinstance(partner, int):
            kwargs["partner_id"] = partner
        elif isinstance(partner, Model):
            kwargs["partner_id"] = partner.id

        defaults = {
            "partner_id": kwargs["partner_id"],
            "date_order": datetime.now(),
            "validity_date": datetime.now() + timedelta(days=30),
            "pricelist_id": env["product.pricelist"].search([], limit=1).id,
            "payment_term_id": env.ref("account.account_payment_term_immediate").id,
            "user_id": env.user.id,
            "team_id": env["crm.team"].search([], limit=1).id,
        }
        defaults.update(kwargs)

        order_lines = defaults.pop("order_line", [])

        order = env["sale.order"].create(defaults)

        if not order_lines:
            order_lines = SaleOrderFactory._create_default_lines(env, order)

        for line_vals in order_lines:
            if isinstance(line_vals, dict):
                line_vals["order_id"] = order.id
                env["sale.order.line"].create(line_vals)

        return order

    @staticmethod
    def _create_default_lines(env: Environment, order: "odoo.model.sale_order") -> list["odoo.values.sale_order_line"]:
        products = ProductFactory.create_batch(env, count=2)
        lines = []

        for product in products:
            lines.append(
                {
                    "order_id": order.id,
                    "product_id": product.product_variant_id.id,
                    "product_uom_qty": random.randint(1, 10),
                    "price_unit": product.list_price,
                }
            )

        return lines

    @staticmethod
    def create_with_shopify_metadata(env: Environment, **kwargs: OdooValue) -> "odoo.model.sale_order":
        defaults = {
            "shopify_order_id": generate_shopify_id(),
            "shopify_order_number": f"#{random.randint(1000, 9999)}",
            "shopify_checkout_id": generate_shopify_id(),
            "shopify_financial_status": "paid",
            "shopify_fulfillment_status": "unfulfilled",
            "shopify_tags": "test,automated",
            "shopify_last_sync": datetime.now(),
        }
        defaults.update(kwargs)

        return SaleOrderFactory.create(env, **defaults)


class ShopifySyncFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.shopify_sync":
        defaults = {
            "mode": kwargs.get("mode", "import_changed_products"),
            "start_time": datetime.now(),
        }
        defaults.update(kwargs)
        return env["shopify.sync"].create(defaults)


class ProductManufacturerFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_manufacturer":
        defaults = {
            "name": generate_unique_name("Test Manufacturer"),
            "is_motor_manufacturer": kwargs.get("is_motor_manufacturer", False),
        }
        defaults.update(kwargs)
        return env["product.manufacturer"].create(defaults)


class ProductConditionFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_condition":
        defaults = {
            "name": kwargs.get("name", generate_unique_name("Test Condition")),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return env["product.condition"].create(defaults)


class MotorStrokeFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.motor_stroke":
        defaults = {
            "name": kwargs.get("name", "4-Stroke"),
            "code": kwargs.get("code", "4"),
        }
        defaults.update(kwargs)
        return env["motor.stroke"].sudo().create(defaults)


class MotorConfigurationFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.motor_configuration":
        defaults = {
            "name": kwargs.get("name", "V6"),
            "code": kwargs.get("code", "V6"),
        }
        defaults.update(kwargs)
        return env["motor.configuration"].sudo().create(defaults)


class DeliveryCarrierFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.delivery_carrier":
        defaults = {
            "name": kwargs.get("name", generate_unique_name("Test Carrier")),
            "delivery_type": kwargs.get("delivery_type", "fixed"),
            "product_id": kwargs.get("product_id") or env.ref("delivery.product_product_delivery").id,
            "fixed_price": kwargs.get("fixed_price", 10.0),
        }
        defaults.update(kwargs)
        return env["delivery.carrier"].create(defaults)


class ProductTagFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_tag":
        defaults = {
            "name": generate_unique_name("Test Tag"),
            "sequence": kwargs.get("sequence", 10),
            "color": kwargs.get("color", random.randint(1, 11)),
        }
        defaults.update(kwargs)
        return env["product.tag"].create(defaults)


class CrmTagFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.crm_tag":
        defaults = {
            "name": generate_unique_name("Test CRM Tag"),
            "color": kwargs.get("color", random.randint(1, 11)),
        }
        defaults.update(kwargs)
        return env["crm.tag"].create(defaults)


class ProductImageFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_image":
        # noinspection SpellCheckingInspection
        defaults = {
            "name": kwargs.get("name", "test_image"),
            "image_1920": kwargs.get(
                "image_1920", "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            ),
        }
        if "product_tmpl_id" not in kwargs and "product_tmpl_id" not in defaults:
            product = ProductFactory.create(env)
            defaults["product_tmpl_id"] = product.id
        defaults.update(kwargs)
        return env["product.image"].create(defaults)


class SaleOrderLineFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.sale_order_line":
        order_id = kwargs.get("order_id")
        if not order_id:
            order = SaleOrderFactory.create(env)
            order_id = order.id

        product_id = kwargs.get("product_id")
        if not product_id:
            product = ProductFactory.create(env)
            product_id = product.product_variant_id.id

        defaults = {
            "order_id": order_id,
            "product_id": product_id,
            "product_uom_qty": kwargs.get("product_uom_qty", random.randint(1, 10)),
            "price_unit": kwargs.get("price_unit", 100.0),
        }
        defaults.update(kwargs)
        return env["sale.order.line"].create(defaults)


class ProductTypeFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_type":
        defaults = {
            "name": generate_unique_name("Test Product Type"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return env["product.type"].create(defaults)


class ProductAttributeFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.product_attribute":
        defaults = {
            "name": generate_unique_name("Test Attribute"),
            "create_variant": kwargs.get("create_variant", "always"),
            "display_type": kwargs.get("display_type", "radio"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return env["product.attribute"].create(defaults)

    @staticmethod
    def create_with_values(
        env: Environment, value_count: int = 3, **kwargs: OdooValue
    ) -> tuple["odoo.model.product_attribute", "odoo.model.product_attribute_value"]:
        attribute = ProductAttributeFactory.create(env, **kwargs)

        values = env["product.attribute.value"].browse()
        for i in range(value_count):
            value = env["product.attribute.value"].create(
                {
                    "name": f"Value {i + 1}",
                    "attribute_id": attribute.id,
                    "sequence": 10 + i,
                }
            )
            values |= value

        return attribute, values


class ResUsersFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.res_users":
        import secrets

        timestamp = datetime.now().timestamp()
        defaults = {
            "name": generate_unique_name("Test User"),
            "login": f"test_user_{timestamp}_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "email": f"test_{timestamp}@example.com",
            "group_ids": [(6, 0, [env.ref("base.group_user").id])],
        }
        defaults.update(kwargs)
        return env["res.users"].create(defaults)


class CurrencyFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.res_currency":
        defaults = {
            "name": kwargs.get("name", f"TST{random.randint(100, 999)}"),
            "symbol": kwargs.get("symbol", "$"),
            "rate": kwargs.get("rate", 1.0),
            "position": kwargs.get("position", "before"),
            "rounding": kwargs.get("rounding", 0.01),
        }
        defaults.update(kwargs)
        return env["res.currency"].create(defaults)


class FiscalPositionFactory:
    @staticmethod
    def create(env: Environment, **kwargs: OdooValue) -> "odoo.model.account_fiscal_position":
        defaults = {
            "name": generate_unique_name("Test Fiscal Position"),
            "sequence": kwargs.get("sequence", 10),
        }
        defaults.update(kwargs)
        return env["account.fiscal.position"].create(defaults)
