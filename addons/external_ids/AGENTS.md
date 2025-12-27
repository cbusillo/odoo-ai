# AGENTS.md — external_ids

Purpose

- Safe helpers and views for inspecting/managing XML IDs (`ir.model.data`).

Key Points

- Read‑only surfaces by default; write operations gated by groups.
- Batch lookups via domain; copy/paste friendly.

Testing

- Unit: resolving IDs to records and back.
- Security: ensure non‑admins can’t unlink core data.

References

- @docs/odoo/security.md, @docs/workflows/debugging.md
