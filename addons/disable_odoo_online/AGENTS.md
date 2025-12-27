# AGENTS.md — disable_odoo_online

Purpose

- Disable Odoo Online features and nudges in on‑prem deployments.

Scope

- Views and actions that surface upsell/online flows.
- System parameters toggled to keep UX local.

Testing

- Verify no Online banners/actions appear in Settings, Apps, or Discuss.
- JS/tours (if any) should assert absence of Online entry points.

References

- @docs/odoo/workflow.md, @docs/policies/coding-standards.md
