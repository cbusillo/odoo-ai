Title: Shopify Sync Patterns

Data synchronization patterns for Shopify integration and external systems.

### Product Synchronization
```python
# Bidirectional product sync
def sync_product_to_shopify(odoo_product):
    """Push Odoo product changes to Shopify"""
    graphql_mutation = build_product_mutation(odoo_product)
    response = execute_shopify_mutation(graphql_mutation)
    update_odoo_shopify_id(odoo_product, response.product.id)

def sync_product_from_shopify(shopify_product):
    """Pull Shopify product changes to Odoo"""
    odoo_product = find_or_create_odoo_product(shopify_product)
    update_odoo_from_shopify_data(odoo_product, shopify_product)
```

### Inventory Synchronization
```python
# Real-time inventory updates
def sync_inventory_levels():
    """Sync inventory between Odoo and Shopify"""
    for variant in get_products_with_inventory_changes():
        update_shopify_inventory(variant)
        log_sync_activity(variant, 'inventory_sync')
```

### Order Processing
```python
# Order sync workflow
def process_shopify_order(order_webhook):
    """Process incoming Shopify order"""
    odoo_order = create_odoo_order_from_shopify(order_webhook)
    validate_order_data(odoo_order)
    confirm_order_in_odoo(odoo_order)
    notify_fulfillment_team(odoo_order)
```

## Sync State Management

### Conflict Resolution
```python
def resolve_sync_conflict(odoo_record, external_record):
    """Handle sync conflicts based on timestamp priority"""
    if odoo_record.write_date > external_record.updated_at:
        # Odoo is newer, push to external
        sync_to_external(odoo_record)
    else:
        # External is newer, pull to Odoo
        sync_from_external(external_record)
```

### Batch Processing
```python
def batch_sync_products(batch_size=50):
    """Process products in batches to avoid API limits"""
    products = get_pending_sync_products()
    
    for batch in chunk_list(products, batch_size):
        process_product_batch(batch)
        rate_limit_delay()  # Respect API limits
```

### Error Handling
```python
def handle_sync_error(record, error, retry_count=0):
    """Robust error handling for sync operations"""
    if retry_count < MAX_RETRIES:
        schedule_retry(record, retry_count + 1)
    else:
        log_permanent_failure(record, error)
        notify_administrators(record, error)
```

## Sync Monitoring Patterns

### Health Checks
```python
def check_sync_health():
    """Monitor sync system health"""
    return {
        'api_connectivity': test_shopify_connection(),
        'pending_syncs': count_pending_operations(),
        'error_rate': calculate_error_rate(),
        'last_successful_sync': get_last_sync_timestamp()
    }
```

### Performance Metrics
```python
def collect_sync_metrics():
    """Gather sync performance data"""
    return {
        'sync_latency': measure_average_sync_time(),
        'throughput': calculate_records_per_minute(),
        'error_count': count_recent_errors(),
        'api_usage': get_api_quota_usage()
    }
```

## Webhook Processing

### Shopify Webhooks
```python
def process_shopify_webhook(webhook_data):
    """Handle incoming Shopify webhooks"""
    event_type = webhook_data.get('event_type')
    
    handlers = {
        'orders/create': process_order_create,
        'orders/updated': process_order_update,
        'products/update': process_product_update,
        'inventory_levels/update': process_inventory_update
    }
    
    handler = handlers.get(event_type)
    if handler:
        handler(webhook_data)
```

### Webhook Security
```python
def validate_webhook_signature(request):
    """Verify webhook authenticity"""
    signature = request.headers.get('X-Shopify-Hmac-Sha256')
    body = request.get_data()
    expected = calculate_webhook_signature(body)
    
    return hmac.compare_digest(signature, expected)
```

## Data Mapping Patterns

### Field Mapping
```python
SHOPIFY_TO_ODOO_MAPPING = {
    'title': 'name',
    'body_html': 'description',
    'vendor': 'brand_id.name',
    'product_type': 'categ_id.name',
    'tags': 'tag_ids',
    'status': 'sale_ok'
}

def map_shopify_to_odoo(shopify_data):
    """Map Shopify fields to Odoo fields"""
    odoo_data = {}
    for shopify_field, odoo_field in SHOPIFY_TO_ODOO_MAPPING.items():
        if shopify_field in shopify_data:
            odoo_data[odoo_field] = transform_field_value(
                shopify_data[shopify_field], 
                odoo_field
            )
    return odoo_data
```

### Data Transformation
```python
def transform_price_data(shopify_price):
    """Convert Shopify price format to Odoo"""
    # Shopify stores prices as strings in cents
    return float(shopify_price) / 100

def transform_tags(shopify_tags):
    """Convert Shopify tags to Odoo tag records"""
    tag_names = shopify_tags.split(',')
    return [('6', 0, [find_or_create_tag(name.strip()) for name in tag_names])]
```

## Sync Scheduling

### Periodic Sync
```python
def schedule_periodic_syncs():
    """Set up regular sync schedules"""
    schedules = [
        ('product_sync', '*/15 * * * *'),  # Every 15 minutes
        ('inventory_sync', '*/5 * * * *'),  # Every 5 minutes
        ('order_sync', '* * * * *'),        # Every minute
        ('full_reconciliation', '0 2 * * *') # Daily at 2 AM
    ]
    
    for sync_type, cron_expression in schedules:
        schedule_cron_job(sync_type, cron_expression)
```

### Priority-based Sync
```python
def prioritize_sync_operations():
    """Process high-priority syncs first"""
    priorities = ['orders', 'inventory', 'products', 'customers']
    
    for priority in priorities:
        pending_ops = get_pending_operations(priority)
        if pending_ops:
            process_operations(pending_ops)
            if api_rate_limit_exceeded():
                break
```
