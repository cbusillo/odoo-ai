---
title: Odoo Intelligence Tools
---


Purpose

- Use MCP helpers for ORM discovery and reads/writes instead of ad-hoc shell
  access.

When

- Use for model discovery, field metadata, and ORM-powered reads or writes.
- Prefer before opening `odoo-bin shell` or raw SQL.

When not to use

- If the ORM cannot boot or the database is corrupted; use raw `docker exec` or
  SQL for emergency debugging.

Tool order

1. Use odoo-intelligence helpers.
2. Use `odoo-bin shell` for interactive or large exploratory work.
3. Use raw `docker exec` / SQL only as a last resort.
