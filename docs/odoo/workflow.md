---
title: Odoo Workflow & Style
---


Purpose

Project-specific Odoo conventions and rules that are easy to drift from code.

When

- Any time you touch Odoo models, views, or frontend assets.

Field Naming (Custom Models)

- Many2one: use object names without `_id` (e.g., `partner`).
- One2many/Many2many: use plural object names without `_ids` (e.g., `partners`).
- Keep core model field names when extending Odoo (`_inherit`).

Context Flags

- `skip_shopify_sync=True` — use for bulk operations or data fixes to prevent
  sync loops.

Container Paths

- Host `./` maps to container `/volumes/`.
- Odoo core lives at `/odoo/addons/*` inside containers (not on host).
- Custom addons live at `/volumes/addons/*`.

Generated Files (Do Not Modify)

- `addons/product_connect/services/shopify/gql/*` — generated GraphQL client.
- `addons/product_connect/graphql/schema/*` — Shopify schema snapshots.

Views (Odoo 18)

- Use `<list>` for list views (do not add new `<tree>` roots).
- Prefer `invisible`, `readonly`, `required` attributes over legacy
  `attrs`/`states`.
- Use `column_invisible` to hide full columns in list views.

Frontend (Odoo 18)

- Use native ES modules (`@web/...`, `@odoo/...`).
- Do not introduce AMD `odoo.define` modules.
- Do not add `/** @odoo-module */` in new files.

Version Guardrails

- Views: `<list>` roots only (no new `<tree>` roots).
- Views: use `invisible`/`readonly`/`required` and `column_invisible`; avoid
  legacy `attrs`/`states`.
- Frontend: native ESM only; no `odoo.define`.

Related Guides

- `docs/odoo/orm.md` — ORM sources of truth.
- `docs/odoo/security.md` — access rules and controller security.
- `docs/tooling/docker.md` — container usage.
