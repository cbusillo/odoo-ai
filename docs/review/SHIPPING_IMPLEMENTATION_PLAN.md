# Shipping Implementation Plan for Odoo 18

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