---
title: Shopify Integration Guide
---


## Purpose

This page keeps a short, accurate map of the Shopify integration. Use it to
jump into the real code and avoid duplicating behavior here.

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

## Configuration (System Parameters)

- `shopify.shop_url_key`
- `shopify.api_token`
- `shopify.test_store`
- `shopify.webhook_key`

See `addons/product_connect/services/shopify/service.py` and
`addons/product_connect/controllers/shopify_webhook.py` for the lookup logic.

## Related Guides

- `docs/integrations/graphql.md` — GraphQL sources of truth.
- `docs/integrations/shopify-sync.md` — sync sources of truth.
- `docs/integrations/webhooks.md` — webhook sources of truth.
- `docs/odoo/security.md#http-controllers` — controller security patterns.
