---
title: eBay Integration Notes
---

Purpose

- Track current eBay behavior and planned extension points.

Current Behavior

- Current order import behavior (via Shopify note attributes) is documented in
  `docs/integrations/shopify.md` under "eBay orders via Shopify".

Planned Enhancements

- Product-level eBay item/listing identifier field (for example
  `ebay_item_id` or `ebay_listing_id`).
- Computed eBay product URL using `https://www.ebay.com/itm/{item_id}`.
- UI exposure alongside existing external links (Shopify and future platforms).

Data Source Options

- Pull eBay item IDs from eBay API.
- Reuse Shopify metafields if item IDs are mirrored there.
- Manual maintenance in Odoo where no reliable source exists.
- Extract item IDs from incoming order payloads when available.

Open Questions

1. Do Shopify-sourced eBay order payloads include stable eBay item IDs?
2. Are eBay listings consistently keyed by the same SKU used in Odoo?
3. Do we need to support multiple concurrent eBay listings per product?
