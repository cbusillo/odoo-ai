---
title: Shopify Sync Sources of Truth
---


## Purpose

This page is a pointer to the real sync implementation. Keep it short and rely
on code references instead of duplicating behavior.

## Sources of Truth

- `addons/product_connect/models/shopify_sync.py` — sync job model, state
    machine, health checks, and async execution.
- `addons/product_connect/services/shopify/helpers.py` — `SyncMode` definitions
    and resource metadata.
- `addons/product_connect/services/shopify/sync/` — importers, exporters, and
    deleters.
- `addons/product_connect/controllers/shopify_webhook.py` — webhook entry point
    and topic-to-sync mapping.

## Related Guides

- `docs/integrations/shopify.md` — architecture, rate limiting, errors.
- `docs/integrations/webhooks.md` — webhook sources of truth.
