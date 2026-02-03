---
title: Odoo Security Sources of Truth (18)
---


Purpose

Keep security guidance tied to the real code and configuration. Use this page
to jump to the authoritative locations.

When

- Any time you touch ACLs, record rules, or HTTP controllers.

Sources of Truth

- `addons/*/security/ir.model.access.csv` — model access rights.
- `addons/*/security/*.xml` — record rules and security data.
- `addons/*/models/*.py` — `_check_company_auto`, `check_company=True`, and
    field-level controls.
- `addons/shopify_sync/controllers/shopify_webhook.py` — webhook signature
    verification and system-user handoff.

## HTTP Controllers

For controller security patterns, use the Shopify webhook controller as a
reference implementation:

- `addons/shopify_sync/controllers/shopify_webhook.py`

Related Guides

- `docs/odoo/orm.md` — access rules and recordset behavior.
- `docs/odoo/workflow.md` — module layout and security file locations.
- `docs/integrations/shopify.md` — integration entry points.
