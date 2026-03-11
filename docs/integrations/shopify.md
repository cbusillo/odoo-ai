---
title: Shopify Integration Guide
---


Purpose

This page keeps a short, accurate map of the Shopify integration. Use it to
jump into the real code and avoid duplicating behavior here.

When

- Any time you touch Shopify sync, webhooks, or GraphQL operations.

## Sources of Truth

- `addons/shopify_sync/models/shopify_sync.py` — sync job model, queueing,
    health checks, and async execution.
- `addons/shopify_sync/services/shopify/service.py` — API client, rate
    limiting, and `API_VERSION`.
- `addons/shopify_sync/services/shopify/helpers.py` — `SyncMode` values and
    Shopify error types.
- `addons/shopify_sync/services/shopify/sync/` — importers, exporters, and
    deleters.
- `addons/shopify_sync/controllers/shopify_webhook.py` — webhook endpoint
    and topic routing.
- `addons/shopify_sync/graphql/shopify/*.graphql` — GraphQL operations and
    fragments.
- `addons/shopify_sync/services/shopify/gql/` — generated client and models
    (do not edit).

## Sync

- Sync orchestration lives in the sources-of-truth files above.
- Sync runs can be canceled from the UI and will stop at the next safe
  checkpoint; canceled runs move to the `canceled` state.

## eBay Orders via Shopify

Order import inspects the Shopify order `custom_attributes` for a
`Note Attributes` entry. If `eBay Latest Delivery Date` is present, it is used
for `commitment_date`. If an eBay sales record or order ID is present, the
order `source_platform` becomes `ebay` and the identifiers are appended to
`shopify_note`.

See `addons/shopify_sync/services/shopify/sync/importers/order_importer.py`.

## Webhooks

- `addons/shopify_sync/controllers/shopify_webhook.py` — entry point, topic
  routing, and signature verification.
- @docs/odoo/security.md#http-controllers — controller security patterns.

## GraphQL

- `addons/shopify_sync/graphql/shopify/*.graphql` — hand-edited operations
  and fragments.
- `addons/shopify_sync/graphql/graphql.config.yml` points IDE tooling
  at the checked-in Shopify GraphQL schema snapshot under
  `addons/shopify_sync/graphql/schema/`, and the tracked IDE module config must
  keep that schema directory included so PyCharm can resolve it without local
  Shopify secrets.
- Keep Shopify instance secrets in `platform/secrets.toml`, not duplicated in
  root `.env`, so release-time env collision checks stay clean.
- `uv run python docker/scripts/generate_shopify_models.py --context opw \
  --instance local` now loads Shopify credentials from the same layered
  platform env used by runtime commands and rewrites `graphql.config.yml` to
  the freshly generated schema version.
- Checked-in schema snapshots remain under
  `addons/shopify_sync/graphql/schema/` for reference and generated client
  history.
- `addons/shopify_sync/services/shopify/gql/` — generated client and models
  (do not edit).

Regenerate generated code from the repo root:

```bash
uv run python docker/scripts/generate_shopify_models.py
```

That command is the only live Shopify introspection path. PyCharm reads the
local schema snapshot through `graphql.config.yml` instead of introspecting the
remote endpoint directly.

## Configuration (System Parameters)

- `shopify.shop_url_key`
- `shopify.api_token`
- `shopify.test_store`
- `shopify.webhook_key`

See `addons/shopify_sync/services/shopify/service.py` and
`addons/shopify_sync/controllers/shopify_webhook.py` for the lookup logic.

## Environment Override Safety

- `environment_overrides` applies Shopify keys from `ENV_OVERRIDE_SHOPIFY__*`
  during restore/init workflows.
- If Shopify overrides are incomplete, the module clears Shopify config params
  rather than leaving stale values.
- `ENV_OVERRIDE_SHOPIFY__PRODUCTION_INDICATORS` blocks production-like
  `shop_url_key` values by default.
- Use `ENV_OVERRIDE_SHOPIFY__ALLOW_PRODUCTION=true` only as an intentional
  break-glass override for prod-candidate environments.

## Images

- Shopify exports use public image URLs. Product image attachments must be
  public so Shopify can fetch them.
- Exporters use the `/web/image` route for product image URLs; `/odoo/image`
  requires authentication in Odoo 19 and will redirect to `/web/login`.

## Related Guides

- @docs/odoo/security.md#http-controllers — controller security patterns.
