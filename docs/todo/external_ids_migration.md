# External IDs Migration — Candidates and Seeding

This doc lists model fields we can migrate into the `external_ids` framework and the systems/templates to seed.

## res.partner (from product_connect)
- `shopify_customer_id` → system `shopify`, resource Customer (numeric ID)
- `shopify_address_id` → system `shopify`, resource CustomerAddress (numeric ID)
- `ebay_username` → system `ebay`, resource User (username as external_id)
- Computed links to replace with URL templates:
  - `shopify_customer_admin_url` → external.system.url (code `admin_customer`)
  - `ebay_profile_url` → external.system.url (code `profile`)

## product.product (from product_connect)
- `shopify_product_id` → system `shopify`, resource Product (numeric ID or GID)
- `shopify_variant_id` → system `shopify`, resource ProductVariant
- `shopify_condition_id` → system `shopify`, metafield `condition` (ID)
- `shopify_ebay_category_id` → system `shopify`, metafield `ebay_category` (ID)
- Optional URL templates: product admin/store pages

## product.image (via ImageMixin)
- `shopify_media_id` → system `shopify`, resource Media (product.image model)

## hr.employee (requested systems)
- `repairshopr` → Employee/User ID
- `discord` → User ID (typically numeric snowflake)
- `timeclock` → Employee ID

## Notes
- Keep `external.system.id_format` conservative at first to avoid false validation errors. Enable regexes when formats are stable.
- Use URL templates instead of computed fields; templates can reference `{id}`, `{gid}`, `{model}`, `{name}`, `{code}`, `{base}`.

