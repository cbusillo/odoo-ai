---
title: Coding Standards (Top‑Level)
---


Purpose

- Define the project-wide coding rules and guardrails.

When

- Before implementing changes or refactors.

Core Rules

- Prefer MCP tools when available in this repo (Inspection, Odoo, Docker).
- Use `uv run` for all tests; never run Python directly.
- Container paths: host `./` maps to container `/volumes/`.
- Runtime baselines (Python/etc.) are defined by repo config, not docs; see
  @docs/tooling/runtime-baselines.md for details.

Odoo 19 Patterns

- Use `<list>` as the root for list views (not `<tree>`).
- Replace legacy `attrs`/`states` with direct attributes (`invisible`,
  `readonly`, `required`) and `column_invisible` for list columns.
- Frontend code should use native ESM (`@web/...`, `@odoo/...`); do not add new
  `odoo.define` modules or `/** @odoo-module */` in new ESM files.
- Type hints are required at API boundaries (function signatures + public data
  shapes). Prefer local inference when clear.
- Zero-warning acceptance gate; use JetBrains `noinspection` only when narrowly
  justified (prefer fixing root causes; see @docs/style/python.md).
- Docs-as-code: when code behavior changes, update affected pages and
  cross-references in the same PR.

Descriptive Code (Naming & DRY)

- Prefer clear, descriptive names over abbreviations: functions as verbs,
  objects as nouns.
- Follow language conventions: Python `snake_case`, JS `camelCase` for
  variables/functions, `PascalCase` for classes.
- One responsibility per function; short functions you can read like English.
- DRY: extract shared logic into helpers; avoid duplicating code/queries/selectors.
- Prefer code that needs no comments. If a comment explains "what" the code
  does, rename or refactor so the code reads clearly. Reserve comments for
  "why", constraints, or decision links.
- Keep code and configs non-redundant and low-noise: avoid explicit defaults or
  repeated attributes when behavior is already clear.

Project Deviation: Relational Field Naming

- New custom models use record-style names for relational fields without
  `_id`/`_ids` suffixes: Many2one `partner` not `partner_id`; One2many/
  Many2many `partners` not `partner_ids`.
- Rationale: the ORM returns recordsets, so names describe objects, not column types.
- Exceptions:
  when extending core models, never rename existing fields; when
  interoperability depends on conventional names, follow the upstream field
  names.

Style Pages

- @docs/style/python.md — Python
- @docs/style/javascript.md — JavaScript
- @docs/style/testing.md — Testing

Odoo Canon

- @docs/odoo/orm.md, @docs/odoo/security.md, @docs/odoo/performance.md, @docs/odoo/workflow.md
