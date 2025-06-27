# Shipping Implementation Plan for Odoo 18

## STATUS: CORE IMPLEMENTATION COMPLETED ✓

### What's Done
- ✅ All delivery products and carriers created
- ✅ 100% shipping method mapping coverage (11,632 orders)
- ✅ Order importer updated with shipping fields
- ✅ Sale order views created
- ✅ Security access configured
- ✅ No catch-all - errors on unknown methods as designed

### What's Pending
- ⚠️ Inventory sync issue (documented in INVENTORY_SYNC_CONCERN.md)
- 📝 Migration scripts for existing orders
- 📊 Analytics views and reports
- 🔧 Performance optimizations
- 🧪 Comprehensive test suite

## Overview
Complete plan for implementing shipping functionality with Odoo 18's new delivery modules, based on historical order data analysis.

## Key Decisions Made

### 1. Field Naming for Shipping Costs
- `shipping_charge` - Amount charged to customer for shipping
- `shipping_paid` - Actual amount paid to shipping carrier  
- `shipping_margin` - Computed field (charge - paid)
- NOT using generic names like "shipping_cost"

### 2. Error Handling Strategy
- **NO CATCH-ALL CARRIER** - Unknown shipping methods should error
- Current behavior (raises `ShopifyDataError`) is perfect
- Sync job will fail and notify when new methods appear
- This forces us to properly map new shipping methods

### 3. Module Dependencies
- Will use `delivery_ups_rest` and `delivery_usps_rest` (Odoo 18 versions)
- Legacy delivery modules are deprecated
- Add to `__manifest__.py` depends list

### 4. Implementation Method
- Use **data XML files** not migrations
- Reasons:
  - Master data that should be version-controlled
  - Can be loaded on new installations
  - Easier to maintain than migrations
  - Can use `noupdate="1"` to preserve customizations

## Shipping Methods Analysis

### From orders_export_1.csv (60,000+ orders):

#### High Volume Methods
1. Empty/blank - 39,781 orders
2. "Low" - 9,794 orders (needs clarification - likely economy/free)
3. "Standard Shipping" - 9,096 orders
4. "UPS Ground" - 1,186 orders

#### UPS Methods (11 variants)
- UPS Ground / UPs Ground (typo) / UPS Ground - Crate
- UPS 2nd Day Air / UPS 3 Day Select
- UPS Next Day Air / UPS Next Day Air Saver
- UPS Standard
- UPS Worldwide Expedited / Express / Saver

#### USPS Methods (8 variants)
- USPS Ground Advantage / USPS Parcel Select Ground
- USPS Priority Mail / USPS Priority Mail (eBay GSP)
- USPS Priority Mail International
- USPS First Class Package (multiple variants)
- USPS First-Class Package International

#### Freight Methods (6 variants)
- Flat Rate Freight
- Freight / Freight Shipping / Freight Shipment
- Freight - Commercial Address Or Local Freight Hub
- Freight Via Southeastern To Local Hub

#### Special Handling
- In Store Pickup - Must Schedule Appointment
- Local Pickup / Warehouse
- Customer/Buyer to arrange shipping (4 variants)
- Free Shipping variants (7 different)

#### Problematic Values
- Numbers: 580111, 60139-2080, 90040-3024
- Platform names: "ebay", "web", "shopify_draft_order"
- Price: "$ 20 shipping"
- "0.00", "" (empty string)

## Implementation Details

### 1. File Structure
```
data/
├── delivery_products.xml      # Service products backing carriers
├── delivery_carriers.xml      # Carrier configurations
└── delivery_carrier_mappings.xml  # Platform-specific mappings
```

### 2. Mapping Strategy
- Normalize names (lowercase, trim)
- Group similar methods under single carriers
- Map typos and variants to correct carrier
- Example: "UPs Ground", "ups ground", "UPS Ground - Crate" → all map to same UPS Ground carrier

### 3. Required Model Extensions

#### sale.order
```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    # eBay Integration
    ebay_sales_record_number = fields.Char(string="eBay Sales Record #", copy=False)
    ebay_order_id = fields.Char(string="eBay Order ID", copy=False)
    source_platform = fields.Selection([
        ('shopify', 'Shopify'),
        ('ebay', 'eBay'), 
        ('manual', 'Manual')
    ], string="Source Platform")
    
    # Shipping Costs
    shipping_charge = fields.Monetary(string="Shipping Charged to Customer")
    shipping_paid = fields.Monetary(string="Shipping Paid to Carrier")
    shipping_margin = fields.Monetary(string="Shipping Margin", compute="_compute_shipping_margin")
    
    # ShipStation Integration (future)
    shipstation_order_id = fields.Char(string="ShipStation Order ID", copy=False)
    shipping_tracking_numbers = fields.Text(string="Tracking Numbers")
```

### 4. Order Importer Updates
- Parse Note Attributes for eBay Sales Record Number
- Extract eBay order information
- Set source_platform based on order source
- Import shipping charge from CSV
- Handle all shipping method variants

## Critical Implementation Details

### Delivery Products Structure
Each carrier service needs:
- **Unique product ID** (e.g., `product_delivery_ups_ground`, `product_delivery_ups_2day`)
- These are service products that back the delivery carriers
- They show up as line items on orders
- MUST have unique IDs to avoid conflicts

### Delivery Carrier Mappings
Key understanding about `_normalise_carrier_name()` in order_importer.py:
- Already converts to lowercase
- Removes punctuation (except hyphens and spaces)
- Strips whitespace
- Uses casefold() for unicode handling

Examples of normalization:
- "UPS Ground" → "ups ground"
- "UPS® Ground™" → "ups ground" 
- "UPS Ground - Crate" → "ups ground crate"
- "USPS Priority Mail®" → "usps priority mail"
- "Free Shipping!" → "free shipping"

**Important**: Since normalization is consistent across platforms, we may only need ONE mapping per unique normalized name, not separate mappings for each platform.

### Testing Before Implementation
Before creating all XML data files:
1. Test on dev database to verify delivery module behavior
2. Validate normalization logic with real shipping names
3. Check if platform-specific mappings are needed
4. Ensure no conflicts with existing data
5. Test with sample orders from CSV
6. Verify carrier → product → order line relationship works correctly

## ShipStation Integration Preparation
- Orders need unique identifiers for matching
- Track both quoted and actual shipping costs
- Support multiple tracking numbers per order
- Update mechanism must be idempotent

## Testing Strategy
1. Import historical orders with all shipping variants
2. Verify no duplicate carriers created
3. Test unknown method error handling
4. Ensure eBay data properly extracted
5. Validate shipping cost calculations

## Future Considerations
- When ShipStation integration is added:
  - Match orders by name/reference
  - Update shipping_paid with actual costs
  - Add tracking numbers
  - Preserve original shipping_charge

## Additional Implementation Requirements

### Security & Access Control
- Add `delivery.carrier.service.map` to `security/ir.model.access.csv`
- Define access rights: 
  - Sales User: read only
  - Sales Manager: full access
  - System Admin: full access including mappings
- Field-level permissions for sensitive shipping cost data

### Data Migration Strategy
- Create migration script `migrations/18.0.6.3/post-migrate.py`
- Backfill `source_platform` field:
  - Orders with `shopify_order_id` → 'shopify'
  - Orders with note containing "eBay" → 'ebay'
  - Others → 'manual'
- Extract eBay order IDs from existing order notes
- Import historical shipping costs if available in external data

### Reporting & Analytics Views
Create `views/shipping_reports.xml` with:
- Shipping margin analysis by platform
- Carrier usage statistics
- Cost trends over time
- Platform comparison dashboard
- Negative margin alerts

### Performance Optimizations
```xml
<!-- data/shipping_indexes.xml -->
<record id="idx_delivery_carrier_service_map_lookup" model="ir.model.constraint">
    <field name="name">idx_delivery_carrier_service_map_lookup</field>
    <field name="model_id" ref="model_delivery_carrier_service_map"/>
    <field name="type">u</field>
    <field name="definition">CREATE INDEX idx_delivery_carrier_service_map_lookup 
        ON delivery_carrier_service_map(platform, external_name);</field>
</record>
```

### Data Validation
```python
# In sale.order model
@api.constrains('shipping_charge', 'shipping_paid')
def _check_shipping_costs(self):
    for order in self:
        if order.shipping_paid > order.shipping_charge * 1.5:
            raise ValidationError("Shipping paid exceeds charge by more than 50%")
        if order.shipping_margin < -100:
            raise ValidationError("Shipping loss exceeds $100")

@api.constrains('ebay_order_id')
def _check_ebay_order_format(self):
    pattern = re.compile(r'^\d{2}-\d{5}-\d{5}$')
    for order in self:
        if order.ebay_order_id and not pattern.match(order.ebay_order_id):
            raise ValidationError("Invalid eBay order ID format")
```

### Audit Trail Configuration
Add to shipping cost fields:
```python
shipping_charge = fields.Monetary(
    string="Shipping Charged to Customer",
    track_visibility='onchange'
)
shipping_paid = fields.Monetary(
    string="Shipping Paid to Carrier", 
    track_visibility='onchange'
)
```

### Multi-Currency Handling
- Shipping costs must use order's currency
- Margin calculation considers exchange rates
- Add currency_id to shipping cost fields if needed

### Returns & Refunds
Additional fields needed:
```python
return_shipping_charge = fields.Monetary(string="Return Shipping Charged")
return_shipping_paid = fields.Monetary(string="Return Shipping Paid")
shipping_refunded = fields.Monetary(string="Shipping Refunded to Customer")
```

### Error Recovery Mechanism
- Create `shipping.import.error` model to queue failed mappings
- Cron job to retry failed imports
- Email notification when new unmapped methods appear
- Admin interface to bulk-map similar methods

### Comprehensive Testing Strategy
1. **Unit Tests** (`tests/test_shipping.py`):
   - Test all 50+ carrier name normalizations
   - Validate shipping margin calculations
   - Test currency conversions
   - Verify constraint validations

2. **Integration Tests** (`tests/test_shipping_import.py`):
   - Import sample CSV with all shipping variants
   - Verify no duplicate carriers created
   - Test error handling for unknown methods
   - Validate eBay data extraction

3. **Performance Tests**:
   - Import 10,000 orders with varied shipping
   - Measure lookup performance
   - Test bulk operations

4. **Edge Cases**:
   - Zero shipping costs
   - Negative shipping (discounts)
   - Missing shipping methods
   - Malformed data

### Implementation Priority
1. **High Priority** (Week 1):
   - Core fields and models
   - Basic carrier mappings
   - Order importer updates
   - Security configuration

2. **Medium Priority** (Week 2):
   - Views and reports
   - Migration scripts
   - Validation constraints
   - Basic tests

3. **Low Priority** (Week 3):
   - Advanced analytics
   - Error recovery
   - Return shipping
   - Performance optimization