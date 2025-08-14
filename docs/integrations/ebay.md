# eBay Integration Notes

## Current State

We're currently extracting eBay order information from Shopify orders (via the Note Attributes field), which includes:

- eBay Sales Record Number
- eBay Order ID
- Delivery dates

## Future Enhancements

### eBay Product URLs

Currently we have a Shopify URL link on product pages. To add eBay product URLs, we would need:

1. **eBay Item Number Storage**: Add a field to store the eBay item number on `product.template` or `product.product`
    - Field name suggestion: `ebay_item_id` or `ebay_listing_id`

2. **URL Generation**: eBay item URLs follow the pattern:
    - `https://www.ebay.com/itm/{item_id}`

3. **Data Source**: We need to determine how to get the eBay item IDs:
    - From eBay API directly?
    - From Shopify metafields if they're storing it?
    - From manual entry?
    - From order line item data (if eBay sends item IDs with orders)?

### Implementation Considerations

- Similar to `shopify_product_url` computed field
- Would need a `ebay_product_url` computed field
- Add to product form view alongside Shopify URL
- Consider adding a generic "External URLs" section for multiple platforms

### Open Questions

1. Does the eBay order data in Shopify include item IDs we could extract?
2. Are products listed on eBay with the same SKU as in Odoo?
3. Do we need to support multiple eBay listings for the same product?