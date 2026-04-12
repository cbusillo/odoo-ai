# AGENTS.md — shopify_sync

Purpose

- Shopify integration: sync products, customers, and orders.

Do Not Modify

- `addons/opw/shopify_sync/services/shopify/gql/*` — generated GraphQL client files.
- `addons/opw/shopify_sync/graphql/schema/*` — Shopify schema snapshots.

Key Points

- Keep Shopify logic isolated from client-specific addons.
- Use `external_ids` for Shopify/eBay identifiers.

Testing

- Unit: helpers and sync state machine.
- Integration: importer/exporter flows, idempotency.

References

- @docs/integrations/shopify.md
