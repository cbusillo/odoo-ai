Title: Coding Standards (Top‑Level)

Core Rules

- Prefer MCP tools when available in this repo (Inspection, Odoo, Docker).
- Use `uv run` for all tests; never run Python directly.
- Container paths: host `./` maps to container `/volumes/`.
- Runtime baselines (Python/etc.) are defined by repo config, not docs; see
  @docs/tooling/runtime-baselines.md.
- Type hints are required at API boundaries (function signatures + public data
  shapes). Prefer local inference when clear.
- Zero‑warning acceptance gate; use JetBrains `noinspection` only when narrowly justified
  (see @docs/style/python.md).
- Docs-as-code: keep docs accurate. When code behavior changes, update affected pages and cross‑references in the same
  PR.

Descriptive Code (Naming & DRY)

- Prefer clear, descriptive names over abbreviations: functions as verbs (do/process/compute), objects as nouns.
- Follow language conventions: Python `snake_case`, JS `camelCase` for variables/functions, `PascalCase` for classes.
- One responsibility per function; short functions you can read like English.
- DRY: extract shared logic into helpers; avoid duplicating code/queries/selectors.
- Prefer code that needs no comments. If a comment explains “what” the code does, rename or refactor so the code reads
  clearly. Reserve comments for “why/constraints/links to decisions”.

Project Deviation: Relational Field Naming

- New custom models use record‑style names for relational fields without `_id`/`_ids` suffixes:
    - Many2one: `partner` (not `partner_id`)
    - One2many/Many2many: `partners` (not `partner_ids`)
- Rationale: the ORM returns recordsets, so names describe objects, not column types.
- Exceptions:
    - When extending core models, never rename existing fields; keep Odoo’s original names.
    - When interoperability requires conventional names (e.g., view inheritance from core), follow the upstream field
      names.

Style Pages

- @docs/style/python.md — Python
- @docs/style/javascript.md — JavaScript
- @docs/style/testing.md — Testing

Odoo Canon

- @docs/odoo/orm.md, @docs/odoo/security.md, @docs/odoo/performance.md, @docs/odoo/workflow.md
