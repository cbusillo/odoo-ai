---
title: Webhook Sources of Truth
---



## Purpose

This page is a pointer to the real webhook implementation details. Keep the
code references here small and avoid duplicating behavior.

## Sources of Truth

- `addons/product_connect/controllers/shopify_webhook.py` — webhook entry
  point, signature verification, routing to sync.
- `docs/odoo/security.md#http-controllers` — request validation patterns and
  access control.
- `docs/integrations/shopify-sync.md` — sync-mode mapping for webhook topics.

## Related Guides

- `docs/integrations/shopify.md` — integration overview and troubleshooting.
