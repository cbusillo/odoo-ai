---
title: Documentation Standards
---


Purpose

- Define how documentation should be structured and linked.

When

- Any time documentation is added or updated.

Goals

- Small topic pages with stable anchors. Prefer linking by handle.
- Prioritize routing and clarity over verbose metadata.

Structure

- Front matter is optional; if used, keep it to `title` only.
- Prefer a short Purpose line, then 2-5 concise sections.
- Short headings; minimal examples; consistent anchor names.

Handles

- Use path+anchor: @docs/odoo/orm.md#batch-operations; avoid pasting large
  excerpts.

Maintenance

- Update docs whenever behavior changes; include cross-reference updates in the
  same PR.
- Keep docs small; link to authoritative code or docs instead of copying.
