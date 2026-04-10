---
title: External IDs Guide
---

Purpose

This page defines the intended shape of `external_ids` so new addons use the
same API and do not drift back toward bespoke `*_id` fields or helper
wrappers.

When

- Any time you add or migrate external identity on an Odoo model.
- Any time you touch `external.id`, `external.id.mixin`, or caller addons that
  read/write external mappings.

## Principles

- `external.id` is the canonical storage model for external identity.
- External identity belongs in mappings, not mirrored native fields, unless the
  field carries real business meaning beyond identity.
- Shared API paths must respect normal access control.
- If a caller needs elevated writes, make `sudo()` explicit at the integration
  boundary.
- Prefer one fluent API over addon-local wrapper layers.

## Preferred Usage

Use the generic fluent path for concrete record code:

- `record.external.shopify.product.id`
- `record.external.shopify.product.admin_url`
- `record.external.ebay.profile.profile_url`

Use bound APIs when a model has one obvious primary external identity:

- `record.external_reference.id`
- `record.external_id`
- `record.external_id_record`
- `env["sale.order"].search_by_bound_external_id("12345")`

Use model-level ORM helpers as the canonical lookup path:

- `env["product.product"].search_by_external_id("shopify", "12345", resource="variant")`
- `env["sale.order.line"].map_by_external_id("shopify", ["101", "102"], resource="order_line")`
- `env["product.product"].search(env["product.product"].domain_by_external_id("shopify", "12345", resource="variant"), limit=1)`

Use model-level fluent lookups as optional sugar when they read better:

- `env["product.product"].external["shopify"]["variant"].get("12345")`
- `env["product.product"].external_lookup.shopify.variant["12345"]`
- `env["product.type"].external.ebay.category.get("67890")`
- `env["sale.order.line"].external.shopify.order_line.map([...])`

## Caller Rules

- Do not add alias properties like `shopify_external` or `ebay_external`
  unless the generic fluent path is materially worse.
- Do not add `get_shopify_*`, `set_shopify_*`, or `search_by_shopify_*`
  compatibility wrappers once callers can use the fluent or bound API.
- When migrating a native external-ID field into `external_ids`, migrate the
  data, update callers, and remove the old field from both code and schema.

## Write Semantics

- `set_external_id(...)` is the canonical generic write path.
- `reference.id = value` is the canonical fluent write path.
- `reference.id = None` clears the mapping by archiving it.
- Numeric inputs are accepted and normalized to strings by the fluent setter.
- Shared APIs do not elevate privileges implicitly; caller code should make any `sudo()` explicit at the integration boundary.

## Resource-Specific References

Addon-specific resource reference classes are the right place for richer URL or
resource behavior, for example Shopify product admin/store URLs or eBay profile
URLs.

Register those behaviors through `register_external_system_reference(...)`
instead of adding caller-local helper functions.

## Anti-Patterns

- Native mirrored fields like `shopify_product_id`, `ebay_order_id`, or
  `*_external_id` left behind after migration.
- Hidden `sudo()` inside shared abstraction layers.
- Generated API artifacts used as a constants warehouse.
- Generic `external_ids` code that knows about one specific caller addon's
  business exception instead of using an extension point.
