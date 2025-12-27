# AGENTS.md — product_connect

Purpose

- Shopify integration addon: product, inventory, order sync via Admin GraphQL.

Do Not Modify

- `services/shopify/gql/*` — generated GraphQL client files
- `graphql/schema/*` — Shopify schema definitions

Key Areas

- Models: product and sync models (flags, timestamps, queues)
- Services: GraphQL client usage; cost/throttleStatus backoff; bulk operations
- Webhooks: inbound processing (orders, products, inventory)

Sync Patterns

- Use context flag `skip_shopify_sync=True` to prevent loops when writing synced records.
- Prefer incremental sync; reserve full sync for initialization.

Testing

- Unit/integration tests for import/export flows; Hoot tests for any frontend bits.
- Gate with JSON: parse `tmp/test-logs/latest/summary.json`.

References

- @docs/integrations/graphql.md, @docs/integrations/shopify-sync.md, @docs/integrations/webhooks.md
