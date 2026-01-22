---
title: Shopify Integration Guide
---


Purpose

This page keeps a short, accurate map of the Shopify integration. Use it to
jump into the real code and avoid duplicating behavior here.

When

- Any time you touch Shopify sync, webhooks, or GraphQL operations.

## Sources of Truth

- `addons/product_connect/models/shopify_sync.py` — sync job model, queueing,
    health checks, and async execution.
- `addons/product_connect/services/shopify/service.py` — API client, rate
    limiting, and `API_VERSION`.
- `addons/product_connect/services/shopify/helpers.py` — `SyncMode` values and
    Shopify error types.
- `addons/product_connect/services/shopify/sync/` — importers, exporters, and
    deleters.
- `addons/product_connect/controllers/shopify_webhook.py` — webhook endpoint
    and topic routing.
- `addons/product_connect/graphql/shopify/*.graphql` — GraphQL operations and
    fragments.
- `addons/product_connect/services/shopify/gql/` — generated client and models
    (do not edit).

## Sync

- `addons/product_connect/models/shopify_sync.py` — state machine, health
  checks, and async execution.
- `addons/product_connect/services/shopify/helpers.py` — `SyncMode` and resource
  metadata.
- `addons/product_connect/services/shopify/sync/` — importers, exporters, and
  deleters.

## eBay Orders via Shopify

Order import inspects the Shopify order `custom_attributes` for a
`Note Attributes` entry. If `eBay Latest Delivery Date` is present, it is used
for `commitment_date`. If an eBay sales record or order ID is present, the
order `source_platform` becomes `ebay` and the identifiers are appended to
`shopify_note`.

See `addons/product_connect/services/shopify/sync/importers/order_importer.py`.

## Webhooks

- `addons/product_connect/controllers/shopify_webhook.py` — entry point, topic
  routing, and signature verification.
- `docs/odoo/security.md#http-controllers` — controller security patterns.

## GraphQL

- `addons/product_connect/graphql/shopify/*.graphql` — hand-edited operations
  and fragments.
- `addons/product_connect/services/shopify/gql/` — generated client and models
  (do not edit).

Regenerate generated code from the repo root:

```bash
uv run python docker/scripts/generate_shopify_models.py
```

## Configuration (System Parameters)

- `shopify.shop_url_key`
- `shopify.api_token`
- `shopify.test_store`
- `shopify.webhook_key`

See `addons/product_connect/services/shopify/service.py` and
`addons/product_connect/controllers/shopify_webhook.py` for the lookup logic.

## Images

- Shopify exports use public image URLs. Product image attachments must be
  public so Shopify can fetch them.
- Exporters use the `/web/image` route for product image URLs; `/odoo/image`
  requires authentication in Odoo 19 and will redirect to `/web/login`.

## Related Guides

- `docs/odoo/security.md#http-controllers` — controller security patterns.
