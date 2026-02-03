# AGENTS.md — opw_custom

Purpose

- OPW-specific product workflows, multigraph analytics, and inventory tools.

Key Areas

- Multigraph view/model/controller and analytics actions.
- Product processing views and label/report helpers.
- OPW-only overrides for product handling and inventory flows.

Sync Patterns

- Shopify sync lives in `shopify_sync`; avoid Shopify-specific logic here.
- Motors workflows live in `marine_motors`; keep OPW-specific glue only.

Testing

- Unit/integration tests for OPW workflows; Hoot tests for frontend views.
- Gate with JSON: parse `tmp/test-logs/latest/summary.json`.

References

- @docs/odoo/workflow.md
- @docs/odoo/security.md#http-controllers
