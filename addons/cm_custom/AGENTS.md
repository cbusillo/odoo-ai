# AGENTS.md — cm_custom

Purpose

- Project‑specific small customizations (fields, views, defaults). Keep diffs minimal.

Guidelines

- Use `_inherit` with the least intrusive overrides.
- Batch writes/imports with `with_context(skip_shopify_sync=True)` when touching synced models.

Testing

- Unit tests for each field/constraint; tour only when UI behavior changes.

References

- @docs/odoo/workflow.md, @docs/policies/acceptance-gate.md
