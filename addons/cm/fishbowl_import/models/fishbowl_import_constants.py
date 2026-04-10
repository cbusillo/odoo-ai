EXTERNAL_SYSTEM_CODE = "fishbowl"
EXTERNAL_SYSTEM_APPLICABLE_MODEL_XML_IDS = (
    "base.model_res_partner",
    "product.model_product_template",
    "sale.model_sale_order",
    "sale.model_sale_order_line",
    "purchase.model_purchase_order",
    "purchase.model_purchase_order_line",
    "stock.model_stock_picking",
    "stock.model_stock_move",
    "uom.model_uom_uom",
)

RESOURCE_ADDRESS = "address"
RESOURCE_CUSTOMER = "customer"
RESOURCE_VENDOR = "vendor"
RESOURCE_PART = "part"
RESOURCE_PRODUCT = "product"
RESOURCE_UNIT = "uom"
RESOURCE_SALES_ORDER = "so"
RESOURCE_SALES_ORDER_LINE = "soitem"
RESOURCE_PURCHASE_ORDER = "po"
RESOURCE_PURCHASE_ORDER_LINE = "poitem"
RESOURCE_SHIPMENT = "ship"
RESOURCE_SHIPMENT_LINE = "shipitem"
RESOURCE_RECEIPT = "receipt"
RESOURCE_RECEIPT_LINE = "receiptitem"

LEGACY_BUCKET_SHIPPING = "shipping"
LEGACY_BUCKET_FEE = "fee"
LEGACY_BUCKET_DISCOUNT = "discount"
LEGACY_BUCKET_MISC = "misc"
LEGACY_BUCKET_ADHOC = "adhoc"

IMPORT_CONTEXT: dict[str, bool] = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
    "mail_create_nosubscribe": True,
    "sale_no_log_for_new_lines": True,
    "skip_shopify_sync": True,
    "skip_procurement": True,
}
