# Codex Task Template

Goal

- State the minimal outcome (feature/fix) and scope.

Context

- Project rules: AGENTS.md, CLAUDE.md, docs/style/ODOO.md, docs/style/TESTING.md.
- Odoo 18 canon: docs/odoo18/API_PATTERNS.md, docs/odoo18/SECURITY_PATTERNS.md, docs/odoo18/PERFORMANCE_ORM.md.
- Local examples (optional): addons/product_connect, addons/external_ids.

Task

1) Implement …
2) Tests …
3) Run tests: `uv run test run --json` (or `uv run test unit`) and iterate until green.
4) Run IDE inspection (if MCP inspection is available): trigger → wait → get problems and fix until clean.

Constraints & Tools

- Prefer structured edits (Edit/Write). If edits are blocked in this session, fall back to Bash here‑docs for file
  writes.
- Prefer `uv run test run --json` to launch/wait/gate in one call. For targeted phases, use `uv run test <phase>`.
- If Inspection MCP is available, use it to lint/inspect dynamic Odoo types.

Definition of Done (Zero‑Warning Policy)

- Tests pass locally.
- MCP inspection shows 0 errors/warnings/weak_warnings/infos for touched files; only use targeted `noinspection` with
  one‑line justification for true false positives.
- Odoo 18 checklist items are satisfied for fields/compute/views.
- Return a brief report: Decision • Diffs/Paths • Test summary • Inspection summary • Risks/next steps.
