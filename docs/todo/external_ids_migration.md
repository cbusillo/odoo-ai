---
title: External IDs Migration — Candidates and Seeding
---


Status: blocked — awaiting migration decision and timeline.

This doc lists model fields we can migrate into the `external_ids` framework
and the systems/templates to seed.

Current defaults live in `addons/external_ids/data/external_systems.xml`.
If we consolidate Shopify admin/store into a single system, use the
`external.system.url.base_url` override per template to keep both URLs without
duplicating external IDs.

## res.partner (from product_connect)

- `shopify_customer_id` → system `shopify`, resource `customer` (numeric ID)
- `shopify_address_id` → system `shopify`, resource `customer_address`
  (numeric ID)
- `ebay_username` → system `ebay`, resource `default` (username as `external_id`)
- Computed links to replace with URL templates:
  `shopify_customer_admin_url` → external.system.url (code `customer_admin`),
  `ebay_profile_url` → external.system.url (code `profile`)

## product.product (from product_connect)

- `shopify_product_id` → system `shopify`, resource `product`
- `shopify_variant_id` → system `shopify`, resource `product_variant`
- `shopify_condition_id` → system `shopify`, resource `condition` (metafield ID)
- `shopify_ebay_category_id` → system `shopify`, resource `ebay_category`
  (metafield ID)

## product.image (via ImageMixin)

- `shopify_media_id` → system `shopify`, resource `media` (product.image)

## Notes

- Keep `external.system.id_format` conservative at first to avoid false
  validation errors. Enable regexes when formats are stable.
- Shopify systems default to numeric-only IDs; if we need to keep raw GIDs,
  relax `id_format` or store extracted numeric IDs.
- Use URL templates instead of computed fields; templates can reference `{id}`,
  `{gid}`, `{model}`, `{name}`, `{code}`, `{base}`.
- Recommended URL template codes:
  - `customer_admin`, `product_admin` (admin)
  - `product_store` (store)
  - `profile` (eBay)
