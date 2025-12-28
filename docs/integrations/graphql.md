---
title: GraphQL Sources of Truth (Shopify)
---

## Purpose

This page is a short pointer doc. It keeps GraphQL guidance aligned with the
actual operations and generated client code.

## Sources of Truth

- `addons/product_connect/graphql/shopify/*.graphql` — hand-edited operations
  and fragments.
- `addons/product_connect/services/shopify/gql/` — generated client and models
  (do not edit by hand).

## Regenerate Generated Code

From the repo root:

```bash
uv run python docker/scripts/generate_shopify_models.py
```

## Related Guides

- `docs/integrations/shopify.md` — architecture, rate limiting, retries, bulk
  operations.
- `docs/integrations/webhooks.md` — webhook flows and patterns.
