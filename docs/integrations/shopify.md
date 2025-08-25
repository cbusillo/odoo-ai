# Shopify Integration Guide

## Overview

This guide covers the Shopify integration architecture, including data flow patterns, GraphQL boundaries, rate limiting strategies, and debugging techniques.

## Architecture Overview

### Core Components

- **ShopifySync Model** (`shopify_sync.py`) - Central orchestrator for all sync operations
- **Service Layer** (`services/shopify/service.py`) - HTTP client and rate limiting management
- **GraphQL Client** (`services/shopify/gql/`) - Generated GraphQL client code
- **Importers** - Fetch data from Shopify to Odoo
- **Exporters** - Push data from Odoo to Shopify

### Data Flow Patterns

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Shopify API   │◄──►│  Service Layer   │◄──►│  Odoo Models    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                        ┌─────▼─────┐
                        │ Sync Queue │
                        └───────────┘
```

## Sync Patterns

### Sync Modes

The system supports multiple synchronization modes defined in `SyncMode` enum:

**Product Sync Modes:**
- `IMPORT_THEN_EXPORT_PRODUCTS` - Full bidirectional sync (recommended)
- `IMPORT_CHANGED_PRODUCTS` - Import only changed products since last sync
- `EXPORT_CHANGED_PRODUCTS` - Export only changed products since last sync
- `IMPORT_ALL_PRODUCTS` - Full import (use sparingly)
- `EXPORT_ALL_PRODUCTS` - Full export (use sparingly)
- `IMPORT_ONE_PRODUCT` - Single product import by ID
- `EXPORT_BATCH_PRODUCTS` - Export specific product batch

**Order Sync Modes:**
- `IMPORT_ALL_ORDERS` - Full order import
- `IMPORT_CHANGED_ORDERS` - Incremental order import
- `IMPORT_ONE_ORDER` - Single order import

**Customer Sync Modes:**
- `IMPORT_ALL_CUSTOMERS` - Full customer import
- `IMPORT_CHANGED_CUSTOMERS` - Incremental customer import
- `IMPORT_ONE_CUSTOMER` - Single customer import

### Queue System

The sync system uses a robust queue mechanism:

```python
# Create and queue a sync job
sync = env['shopify.sync'].create({
    'mode': 'import_changed_products',
    'state': 'queued'
})

# Run asynchronously
sync.run_async()
```

### State Management

Sync jobs progress through these states:
- `draft` - Initial state
- `queued` - Waiting for execution
- `running` - Currently executing
- `success` - Completed successfully
- `failed` - Failed with errors

## GraphQL Schema and Boundaries

### Generated Code Structure

**DO NOT MODIFY** the following generated files:
- `services/shopify/gql/base_client.py`
- `services/shopify/gql/base_model.py`
- `services/shopify/gql/client.py`
- `services/shopify/gql/enums.py`
- `services/shopify/gql/input_types.py`
- All operation files (e.g., `get_products.py`, `product_set.py`)

These files are generated from GraphQL schema using `ariadne-codegen`.

### Schema Regeneration

To regenerate GraphQL models after schema changes:

```bash
# From project root
python docker/scripts/generate_shopify_models.py
```

### Key GraphQL Operations

**Products:**
- `get_products` - Fetch product data with pagination
- `product_set` - Create/update products
- `delete_product` - Remove products
- `product_reorder_media` - Reorder product images

**Orders:**
- `get_orders` - Fetch order data
- `get_order_ids` - Get order IDs for bulk operations

**Customers:**
- `get_customers` - Fetch customer data

**Bulk Operations:**
- `current_bulk_operation` - Check bulk operation status
- `product_set_bulk_run` - Execute bulk product operations

## Rate Limiting and Retry Strategies

### API Rate Limits

Shopify uses a bucket-based rate limiting system with these settings:

```python
class ShopifyService:
    MIN_API_POINTS = 500        # Minimum points before throttling
    MAX_RETRY_ATTEMPTS = 10     # Maximum retry attempts
    MIN_SLEEP_TIME = 1.0        # Minimum wait time (seconds)
    MAX_SLEEP_TIME = 60.0       # Maximum wait time (seconds)
```

### Throttling Detection

The system monitors rate limits through response headers:

```python
def rate_limit_hook(response: Response) -> None:
    data = response.json()
    throttle_status = data.get("extensions", {}).get("cost", {}).get("throttleStatus", {})
    currently_available = throttle_status.get("currentlyAvailable", 0)
    
    if currently_available < MIN_API_POINTS:
        # Wait for points to restore
        deficit = MIN_API_POINTS - currently_available
        wait_time = deficit / restore_rate
        sleep(wait_time)
```

### Retry Logic

Automatic retries for these error types:
- `ShopifyApiError`
- `OdooDataError`
- `TransactionRollbackError`
- `SerializationFailure`
- `OperationalError`
- `InterfaceError`
- `RequestError`

HTTP status codes that trigger retries: `429, 500, 502, 503, 504`

## Error Handling Patterns

### Exception Hierarchy

```python
UserError
├── OdooDataError
│   ├── OdooMissingSkuError
│   └── ShopifyApiError
│       ├── ShopifyDataError
│       └── ShopifyMissingSkuFieldError
├── ShopifySyncRunFailed
└── ShopifyStaleRunTimeout
```

### Error Context Capture

The system captures comprehensive error context:

```python
class ShopifyApiError(OdooDataError):
    def __init__(self, message: str, *,
                 shopify_record: BaseModel | None = None,
                 shopify_input: BaseModel | None = None,
                 odoo_record: models.Model | None = None):
        # Captures full context for debugging
```

### Stale Run Recovery

Automatically recovers from stale sync runs:

```python
def _fail_stale_runs(self, threshold_seconds: int = 60) -> None:
    # Identifies runs with no activity for threshold period
    # Retries up to MAX_RETRY_ATTEMPTS or marks as failed
```

## Configuration

### Required Settings

Set these parameters in Odoo settings:

```python
# System parameters
shopify.shop_url_key = "your-shop-name"
shopify.api_token = "your-api-token"
shopify.test_store = False  # Set to True for test environments
```

### API Version

Currently using Shopify API version `2025-04`. Update in `ShopifyService.API_VERSION` if needed.

## Common Integration Scenarios

### 1. Product Sync with SKU Validation

```python
# Product import validates SKU format
def _import_one(self, shopify_product: ProductFields) -> bool:
    variant = shopify_product.variants.nodes[0]
    try:
        shopify_sku, bin_location = parse_shopify_sku_field_to_sku_and_bin(variant.sku)
    except ShopifyMissingSkuFieldError:
        logger.warning(f"Missing SKU for product {shopify_product.id}")
        return False
    
    # Find existing product by Shopify ID or SKU
    odoo_product = env["product.product"].search([
        "|",
        ("shopify_product_id", "=", parse_shopify_id_from_gid(shopify_product.id)),
        ("default_code", "=", shopify_sku),
    ], limit=1)
```

### 2. Conditional Updates

```python
# Only update if Shopify data is newer
if shopify_product.updated_at > latest_write_date:
    odoo_product = self.save_odoo_product(odoo_product, shopify_product)
    return True
```

### 3. Image Sync with Status Checking

```python
# Check for processing images before sync
def _has_processing_images(self, shopify_product: ProductFields, 
                          odoo_product: "odoo.model.product_product") -> bool:
    images = shopify_product.media.nodes
    processing_images = [img for img in images if img.status == MediaStatus.PROCESSING]
    if processing_images:
        logger.debug(f"Product {shopify_product.id} has processing images, skipping")
        return True
    return False
```

### 4. Bulk Operations

```python
# Use bulk operations for large datasets
def _check_bulk_operation_status(self) -> bool:
    response = self.service.client.current_bulk_operation()
    operation = response.current_bulk_operation
    
    if operation and operation.status == "RUNNING":
        return False  # Still processing
    return True  # Ready for next operation
```

### 5. Skip Sync Context

```python
# Prevent infinite sync loops
product.with_context(skip_shopify_sync=True).write(values)

# Check context in triggers
if self.env.context.get("skip_shopify_sync"):
    return  # Skip sync operation
```

## Debugging Tips

### 1. Sync Job Monitoring

```python
# Check sync queue status
syncs = env['shopify.sync'].search([('state', 'in', ['queued', 'running'])])
for sync in syncs:
    print(f"Sync {sync.id}: {sync.mode} - {sync.state}")
```

### 2. Error Investigation

```python
# Find failed syncs with details
failed_syncs = env['shopify.sync'].search([('state', '=', 'failed')])
for sync in failed_syncs:
    print(f"Error: {sync.error_message}")
    print(f"Exception: {sync.error_exception}")
    print(f"Traceback: {sync.error_traceback}")
```

### 3. Rate Limit Monitoring

```python
# Check throttle counts
sync = env['shopify.sync'].browse(sync_id)
print(f"Hard throttle count: {sync.hard_throttle_count}")
print(f"Retry attempts: {sync.retry_attempts}")
```

### 4. Product Sync Status

```python
# Check product sync flags
product = env['product.product'].browse(product_id)
print(f"Next export: {product.shopify_next_export}")
print(f"Last exported: {product.shopify_last_exported_at}")
print(f"Shopify ID: {product.shopify_product_id}")
```

### 5. API Response Debugging

Enable debug logging in `services/shopify/service.py`:

```python
# Add to rate_limit_hook
logger.debug(f"Shopify API rate limit status: {throttle_status}")
logger.debug(f"Response data: {data}")
```

## Performance Considerations

### 1. Pagination

Use appropriate page sizes:
- Default: `SHOPIFY_PAGE_SIZE = 250`
- Commit size: `COMMIT_SIZE = 25` (PAGE_SIZE // 10)

### 2. Selective Sync

Filter products for export:

```python
def _find_products_to_export(self):
    return env["product.product"].search([
        ("sale_ok", "=", True),
        ("is_ready_for_sale", "=", True),
        ("is_published", "=", True),
        ("website_description", "!=", False),
        ("type", "=", "consu"),
    ])
```

### 3. Image Processing

Check image status before sync:
- Only sync `MediaStatus.READY` images
- Skip products with `MediaStatus.PROCESSING` images
- Flag `MediaStatus.FAILED` images for re-export

### 4. Transaction Management

Use safe commits and rollbacks:

```python
try:
    # Sync operations
    self._safe_commit()
except Exception:
    self._safe_rollback()
    raise
```

### 5. Advisory Locking

Prevent concurrent syncs:

```python
with self._advisory_lock(self.LOCK_ID) as lock_acquired:
    if not lock_acquired:
        return  # Another sync is running
    # Proceed with sync
```

## Best Practices

### 1. Always Use Context Flags

```python
# Prevent sync loops
record.with_context(skip_shopify_sync=True).write(values)
```

### 2. Validate Data Before Sync

```python
if not product.default_code:
    raise OdooMissingSkuError("Product must have SKU")
```

### 3. Handle Missing Data Gracefully

```python
try:
    sku, bin_location = parse_shopify_sku_field_to_sku_and_bin(variant.sku)
except ShopifyMissingSkuFieldError:
    logger.warning(f"Skipping product without SKU: {product.id}")
    return False
```

### 4. Use Incremental Sync

Prefer incremental over full sync:
- `IMPORT_THEN_EXPORT_PRODUCTS` for regular sync
- `IMPORT_ALL_PRODUCTS` only for initial setup

### 5. Monitor Sync Health

The system automatically creates sync jobs if none exist:

```python
def _is_healthy(mode: SyncMode) -> bool:
    in_flight = self.search_count([("mode", "=", mode.value), ("state", "in", ["queued", "running"])])
    recent = self.search_count([("mode", "=", mode.value), ("state", "=", "success"), ("start_time", ">=", cutoff)])
    return bool(in_flight or recent)
```

## Troubleshooting

### Common Issues

1. **Sync Stuck in Running State**
   - Check for stale runs: automatically handled after 60s
   - Manually reset: `sync.write({'state': 'queued'})`

2. **Rate Limit Errors**
   - System automatically waits for rate limit recovery
   - Check `hard_throttle_count` for frequency

3. **Missing SKUs**
   - Products require valid SKU format: "SKU - BIN"
   - Check `parse_shopify_sku_field_to_sku_and_bin` function

4. **Image Sync Issues**
   - Wait for Shopify image processing to complete
   - Check `MediaStatus` before sync

5. **Duplicate Prevention**
   - System prevents duplicate queued syncs
   - Check `_is_duplicate` logic for batch operations

### Recovery Procedures

1. **Reset Failed Syncs**
```python
failed_syncs = env['shopify.sync'].search([('state', '=', 'failed')])
failed_syncs.write({'state': 'queued', 'retry_attempts': 0})
```

2. **Clear Processing Images**
```python
# Flag products for re-export if images failed
products = env['product.product'].search([('shopify_product_id', '!=', False)])
products.write({'shopify_next_export': True})
```

3. **Manual Sync Trigger**
```python
env['shopify.sync'].create({
    'mode': 'import_then_export_products'
}).run_async()
```

This integration guide provides the foundation for understanding and working with the Shopify sync system. Always test changes in a development environment before applying to production.