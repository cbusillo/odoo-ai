from ..common_imports import datetime
from datetime import timezone
from typing import Any

from ..test_helpers import generate_unique_sku


def deep_update(base_dict: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
            deep_update(base_dict[key], value)
        else:
            base_dict[key] = value


def create_shopify_product_response(
    gid: str = "gid://shopify/Product/123456789",
    title: str = "Test Product",
    description: str = "<p>Test description</p>",
    vendor: str = "Test Vendor",
    product_type: str = "Test Type",
    status: str = "ACTIVE",
    total_inventory: int = 100,
    created_at: str | None = None,
    updated_at: str | None = None,
    variants: list[dict[str, Any]] | None = None,
    media: list[dict[str, Any]] | None = None,
    metafields: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    created_at = created_at or now
    updated_at = updated_at or now

    if variants is None:
        variants = [
            {
                "id": "gid://shopify/ProductVariant/987654321",
                "price": "99.99",
                "sku": generate_unique_sku(),
                "barcode": "123456789012",
                "inventoryItem": {
                    "unitCost": {"amount": "50.00", "currencyCode": "USD"},
                    "measurement": {"weight": {"value": 1.5}},
                },
            }
        ]

    if media is None:
        media = [
            {
                "__typename": "MediaImage",
                "id": "gid://shopify/MediaImage/123",
                "alt": "Test image",
                "status": "READY",
                "originalSource": {"url": "https://example.com/image.jpg"},
                "preview": {"image": {"url": "https://example.com/preview.jpg"}},
            }
        ]

    if metafields is None:
        metafields = []

    base_response = {
        "id": gid,
        "title": title,
        "descriptionHtml": description,
        "vendor": vendor,
        "productType": product_type,
        "status": status,
        "totalInventory": total_inventory,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "media": {"nodes": media},
        "variants": {"nodes": variants},
        "metafields": {"nodes": metafields},
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_variant_response(
    gid: str = "gid://shopify/ProductVariant/987654321",
    price: str = "99.99",
    sku: str | None = None,
    barcode: str | None = "123456789012",
    weight: float = 1.5,
    unit_cost: str = "50.00",
    currency_code: str = "USD",
    **overrides: Any,
) -> dict[str, Any]:
    if sku is None:
        sku = generate_unique_sku()
    base_response = {
        "id": gid,
        "price": price,
        "sku": sku,
        "barcode": barcode,
        "inventoryItem": {
            "unitCost": {"amount": unit_cost, "currencyCode": currency_code},
            "measurement": {"weight": {"value": weight}},
        },
    }

    deep_update(base_response, overrides)
    return base_response


def create_money_bag(amount: str, currency_code: str = "USD") -> dict[str, Any]:
    return {
        "presentmentMoney": {"amount": amount, "currencyCode": currency_code},
        "shopMoney": {"amount": amount, "currencyCode": currency_code},
    }


def create_shopify_address_response(
    gid: str | None = "gid://shopify/CustomerAddress/123",
    name: str | None = "John Doe",
    company: str | None = None,
    address1: str | None = "123 Main St",
    address2: str | None = None,
    city: str | None = "New York",
    province_code: str | None = "NY",
    province: str | None = "New York",
    country_code: str = "US",
    zip_code: str | None = "10001",
    phone: str | None = "+1-415-867-5309",
    **overrides: Any,
) -> dict[str, Any]:
    base_response = {
        "id": gid,
        "name": name,
        "company": company,
        "address1": address1,
        "address2": address2,
        "city": city,
        "provinceCode": province_code,
        "province": province,
        "countryCodeV2": country_code,
        "zip": zip_code,
        "phone": phone,
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_customer_response(
    gid: str = "gid://shopify/Customer/123456789",
    first_name: str | None = "John",
    last_name: str | None = "Doe",
    email: str | None = "john.doe@example.com",
    phone: str | None = "+1-415-867-5309",
    tax_exempt: bool = False,
    tags: list[str] | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    default_address: dict[str, Any] | None = None,
    addresses: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    created_at = created_at or now
    updated_at = updated_at or now

    if tags is None:
        tags = []

    if default_address is None:
        default_address = create_shopify_address_response(phone=phone)

    if addresses is None:
        addresses = [default_address]

    base_response = {
        "id": gid,
        "firstName": first_name,
        "lastName": last_name,
        "defaultEmailAddress": (
            {
                "emailAddress": email,
                "marketingState": "NOT_SUBSCRIBED",
                "marketingOptInLevel": None,
                "marketingUpdatedAt": None,
            }
            if email
            else None
        ),
        "defaultPhoneNumber": (
            {
                "phoneNumber": phone,
                "marketingState": "NOT_SUBSCRIBED",
                "marketingOptInLevel": None,
                "marketingUpdatedAt": None,
            }
            if phone
            else None
        ),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "defaultAddress": default_address,
        "addressesV2": {"nodes": addresses},
        "tags": tags,
        "taxExempt": tax_exempt,
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_order_line_item_response(
    gid: str = "gid://shopify/LineItem/123456789",
    sku: str | None = "008002",
    quantity: int = 1,
    name: str = "Test Product",
    variant_id: str = "gid://shopify/ProductVariant/987654321",
    unit_price: str = "99.99",
    currency_code: str = "USD",
    custom_attributes: list[dict[str, Any]] | None = None,
    discount_allocations: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    if custom_attributes is None:
        custom_attributes = []

    if discount_allocations is None:
        discount_allocations = []

    base_response = {
        "id": gid,
        "sku": sku,
        "quantity": quantity,
        "name": name,
        "variant": {"id": variant_id},
        "originalUnitPriceSet": create_money_bag(unit_price, currency_code),
        "customAttributes": custom_attributes,
        "discountAllocations": discount_allocations,
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_shipping_line_response(
    gid: str = "gid://shopify/ShippingLine/123456789",
    title: str = "Standard Shipping",
    price: str = "10.00",
    currency_code: str = "USD",
    carrier_identifier: str | None = "ups",
    code: str | None = "STANDARD",
    delivery_category: str | None = None,
    is_removed: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    base_response = {
        "id": gid,
        "title": title,
        "originalPriceSet": create_money_bag(price, currency_code),
        "currentDiscountedPriceSet": create_money_bag(price, currency_code),
        "discountedPriceSet": create_money_bag(price, currency_code),
        "carrierIdentifier": carrier_identifier,
        "code": code,
        "deliveryCategory": delivery_category,
        "isRemoved": is_removed,
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_order_response(
    gid: str = "gid://shopify/Order/123456789",
    name: str = "#1001",
    currency_code: str = "USD",
    total_price: str = "109.99",
    subtotal_price: str = "99.99",
    shipping_price: str = "10.00",
    created_at: str | None = None,
    updated_at: str | None = None,
    processed_at: str | None = None,
    closed_at: str | None = None,
    cancelled_at: str | None = None,
    customer: dict[str, Any] | None = None,
    shipping_address: dict[str, Any] | None = None,
    billing_address: dict[str, Any] | None = None,
    line_items: list[dict[str, Any]] | None = None,
    shipping_lines: list[dict[str, Any]] | None = None,
    discount_applications: list[dict[str, Any]] | None = None,
    tax_lines: list[dict[str, Any]] | None = None,
    metafields: list[dict[str, Any]] | None = None,
    note: str | None = None,
    custom_attributes: list[dict[str, Any]] | None = None,
    payment_gateway_names: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    created_at = created_at or now
    updated_at = updated_at or now
    processed_at = processed_at or now

    if line_items is None:
        line_items = [create_shopify_order_line_item_response()]

    if shipping_lines is None:
        shipping_lines = [create_shopify_shipping_line_response()]

    if discount_applications is None:
        discount_applications = []

    if tax_lines is None:
        tax_lines = []

    if metafields is None:
        metafields = []

    base_response = {
        "id": gid,
        "name": name,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "processedAt": processed_at,
        "closedAt": closed_at,
        "cancelledAt": cancelled_at,
        "currencyCode": currency_code,
        "totalPriceSet": create_money_bag(total_price, currency_code),
        "subtotalPriceSet": create_money_bag(subtotal_price, currency_code),
        "totalShippingPriceSet": create_money_bag(shipping_price, currency_code),
        "customer": customer,
        "shippingAddress": shipping_address,
        "billingAddress": billing_address,
        "lineItems": {"nodes": line_items},
        "shippingLines": {"nodes": shipping_lines},
        "fulfillments": [],
        "discountApplications": {"nodes": discount_applications},
        "totalDiscountsSet": create_money_bag("0.00", currency_code),
        "taxLines": tax_lines,
        "metafields": {"nodes": metafields},
        "note": note,
        "customAttributes": custom_attributes or [],
        "paymentGatewayNames": payment_gateway_names or [],
    }

    deep_update(base_response, overrides)
    return base_response


def create_shopify_page_info(has_next_page: bool = False, has_previous_page: bool = False) -> dict[str, Any]:
    return {"hasNextPage": has_next_page, "hasPreviousPage": has_previous_page}


def create_shopify_metafield(
    gid: str = "gid://shopify/Metafield/123",
    key: str = "test_key",
    value: str = "test_value",
    namespace: str = "custom",
) -> dict[str, Any]:
    return {
        "id": gid,
        "key": key,
        "value": value,
        "namespace": namespace,
    }


def create_shopify_product_image(
    gid: str = "gid://shopify/MediaImage/123456789",
    alt: str | None = None,
    status: str = "READY",
    url: str = "https://example.com/image.jpg",
) -> dict[str, Any]:
    return {
        "__typename": "MediaImage",
        "id": gid,
        "alt": alt,
        "status": status,
        "originalSource": {"url": url},
        "preview": {
            "image": {
                "url": url,
            }
        },
    }


def create_shopify_customer(
    gid: str = "gid://shopify/Customer/123456789",
    first_name: str | None = "John",
    last_name: str | None = "Doe",
    email: str | None = "john.doe@example.com",
    phone: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    tax_exempt: bool = False,
    email_marketing_consent: dict[str, Any] | None = None,
    sms_marketing_consent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": gid,
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "phone": phone,
        "note": note,
        "tags": tags or [],
        "taxExempt": tax_exempt,
        "emailMarketingConsent": email_marketing_consent or {"marketingState": "NOT_SUBSCRIBED"},
        "smsMarketingConsent": sms_marketing_consent or {"marketingState": "NOT_SUBSCRIBED"},
    }


def create_shopify_motor_metafields(
    year: str | None = "2023",
    make: str | None = "Yamaha",
    model: str | None = "F150",
    horsepower: str | None = "150",
    serial_start: str | None = "1000",
    serial_end: str | None = "9999",
) -> list[dict[str, Any]]:
    metafields = []

    if year:
        metafields.append({"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_year", "value": year})

    if make:
        metafields.append({"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_make", "value": make})

    if model:
        metafields.append({"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_model", "value": model})

    if horsepower:
        metafields.append({"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_horsepower", "value": horsepower})

    if serial_start:
        metafields.append(
            {"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_serial_start", "value": serial_start}
        )

    if serial_end:
        metafields.append({"id": f"gid://shopify/Metafield/{len(metafields) + 1}", "key": "motor_serial_end", "value": serial_end})

    return metafields
