# 🔗 External Integrations Guide

This document covers integration patterns and implementation details for external platforms.

## 🛍️ Shopify Integration

**Status**: Implemented  
**Agent**: Shopkeeper agent (@docs/agents/shopkeeper.md)  
**Technology**: GraphQL Admin API

### Architecture
- GraphQL client with generated types
- Webhook handlers for real-time updates
- Bulk operations for large datasets
- Rate limit handling with exponential backoff

### Key Features
- Product sync (create, update, archive)
- Variant management with metafields
- Inventory level tracking
- Order import for visibility
- Collection management

## 📦 eBay Integration

**Status**: Planned  
**Technology**: REST API v1

### API Overview
- **Authentication**: OAuth 2.0 with refresh tokens
- **Sandbox**: Available for testing
- **Rate Limits**: 5,000 calls/day for most endpoints

### Key Endpoints

```python
# Inventory API
PUT /inventory/v1/inventory_item/{sku}
PUT /inventory/v1/offer/{offerId}

# Trading API (legacy but needed)
POST /ws/api.dll?callname=ReviseFixedPriceItem

# Fulfillment API
GET /sell/fulfillment/v1/order
```

### Implementation Considerations

1. **SKU as Primary Key**
   - eBay uses SKU, Shopify uses variant ID
   - Map via product.default_code

2. **Category Mapping**
   - eBay requires specific category IDs
   - Build mapping table for motor parts categories

3. **Listing Details**
   - Item specifics (Year/Make/Model/Engine)
   - Condition (New/Used/Refurbished)
   - Return policy requirements

4. **Inventory Sync**
   - Use Inventory API for multi-variation listings
   - Trading API for single items
   - Location-based inventory

5. **Order Import**
   - Similar to Shopify: import for visibility only
   - Map eBay usernames to res.partner
   - Handle eBay messaging system

### Data Model Extensions

```python
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    ebay_item_id = fields.Char("eBay Item ID")
    ebay_category_id = fields.Char("eBay Category")
    ebay_condition = fields.Selection([
        ('1000', 'New'),
        ('3000', 'Used'),
        ('2000', 'Refurbished'),
    ])
    ebay_listing_duration = fields.Selection([
        ('Days_7', '7 Days'),
        ('Days_30', '30 Days'),
        ('GTC', 'Good Till Cancelled'),
    ], default='GTC')
```

### Sync Strategy

```
Odoo Product Changes
    ↓
eBay Sync Service
    ↓
Bulk Update Queue
    ↓
eBay API (Inventory/Trading)
    ↓
Notification Processing
    ↓
Update Odoo Status
```

### Authentication Flow

1. **Initial Setup**
   - Register app in eBay Developer Program
   - Get App ID, Cert ID, Dev ID
   - Implement OAuth flow

2. **Token Management**
   - Store refresh token securely
   - Auto-refresh before expiration
   - Handle token revocation

3. **Environment Config**
   ```python
   EBAY_APP_ID = env['EBAY_APP_ID']
   EBAY_CERT_ID = env['EBAY_CERT_ID']
   EBAY_DEV_ID = env['EBAY_DEV_ID']
   EBAY_SANDBOX = env.get('EBAY_SANDBOX', 'True')
   ```

### Error Handling

- **API Errors**: Specific error codes for inventory issues
- **Validation**: eBay has strict listing requirements
- **Retry Logic**: Handle rate limits and temporary failures

### Testing Strategy

1. **Sandbox Testing**
   - Use sandbox environment first
   - Test all CRUD operations
   - Verify category mappings

2. **Production Rollout**
   - Start with single SKU
   - Monitor API usage
   - Gradual increase in listings

## 🚚 ShipStation Integration

**Status**: Analysis Phase  
**Purpose**: Shipping label generation and tracking

### Considerations
- REST API available
- Supports multiple carriers
- Order status synchronization
- Tracking number updates

## 🏭 Common Integration Patterns

### Authentication Storage
```python
class IntegrationCredential(models.Model):
    _name = 'integration.credential'
    _description = 'External Integration Credentials'
    
    platform = fields.Selection([
        ('shopify', 'Shopify'),
        ('ebay', 'eBay'),
        ('shipstation', 'ShipStation'),
    ])
    key = fields.Char(required=True)
    value = fields.Char(required=True)
    expires_at = fields.Datetime()
```

### Rate Limit Handling
```python
def with_rate_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RateLimitExceeded as e:
            backoff = calculate_exponential_backoff(e.retry_after)
            time.sleep(backoff)
            return func(*args, **kwargs)
    return wrapper
```

### Sync Job Queue
```python
class SyncJob(models.Model):
    _name = 'sync.job'
    _order = 'priority desc, create_date'
    
    platform = fields.Selection([...])
    operation = fields.Selection([
        ('product_create', 'Create Product'),
        ('inventory_update', 'Update Inventory'),
        ('order_import', 'Import Order'),
    ])
    record_id = fields.Integer()
    status = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ])
    retry_count = fields.Integer(default=0)
    last_error = fields.Text()
```

### Webhook Security
```python
def verify_webhook_signature(request, secret):
    """Verify webhook authenticity"""
    if platform == 'shopify':
        hmac_header = request.httprequest.headers.get('X-Shopify-Hmac-Sha256')
        calculated = base64.b64encode(
            hmac.new(secret.encode(), request.httprequest.data, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(hmac_header, calculated)
    elif platform == 'ebay':
        # eBay notification validation
        pass
```

## 📊 Monitoring and Logging

### Integration Dashboard
- API call counts by platform
- Error rates and types
- Sync queue status
- Last successful sync times

### Detailed Logging
```python
_logger.info("Syncing product %s to %s", product.default_code, platform)
_logger.error("API error for %s: %s", platform, error_details)
```

### Performance Metrics
- API response times
- Bulk operation efficiency
- Queue processing speed
- Error recovery success rate

## 🔧 Development Tools

### Testing Utilities
- Mock API responses
- Sandbox environment configs
- Test data generators
- Integration test suites

### Debugging Helpers
- API request/response logging
- Webhook replay functionality
- Manual sync triggers
- Queue inspection tools

## 📚 Additional Resources

- [Shopify Admin API](https://shopify.dev/docs/admin-api)
- [eBay Developer Docs](https://developer.ebay.com/docs)
- [ShipStation API](https://shipstation.docs.apiary.io/)
- Integration test scenarios in `/tests/integration/`