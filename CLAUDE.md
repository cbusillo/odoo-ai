# CLAUDE.md — Project Guide for Claude Code

Purpose

- Give Claude the stable project knowledge it needs to work effectively.

Project Facts (read‑only)

- Odoo 18 Enterprise; custom addons under `addons/`.
- Do not modify generated files: `services/shopify/gql/*`, `graphql/schema/*`.
- Container mounts (compose):
  - Host `./addons` → container `/volumes/addons` (authoritative custom addons path)
  - Host `./docker/scripts` → container `/volumes/scripts`
  - Named volume `data` → container `/volumes/data`
  - Mirrors for IDE/debug: host `./addons` → container `/opt/project/addons`; host `./pyproject.toml` → `/opt/project/pyproject.toml:ro`
- Paths rule: never read `/odoo/*` from host; when container paths are needed, reference `/volumes/*` (or the IDE mirror) via Odoo/Docker tools, not host file ops.

House Rules for Claude

- Keep the main thread clean; delegate focused work to subagents.
- Prefer MCP tools with structured outputs; use shell when needed for project tasks.
- Execution policy:
  - Claude may run `uv run test-*` and other project task wrappers directly when required.
  - Prefer `uv run` wrappers over raw Python; do not invoke `odoo-bin` or `python -m` directly unless explicitly necessary.
  - Use `odoo-intelligence__*` when it provides better structure (e.g., module updates, test runner APIs) or remote/container isolation; use `docker__*` for container status/logs.
- Never run Python directly (`python -m ...`, `pip ...`) in this repo.
- Avoid recursion and self‑delegation; one pass per subagent role.

Delegation Strategy (Subagents)

- Default to delegate for anything non‑trivial; keep the main thread for planning and arbitration.
- Inline (no subagent) is okay for truly trivial, single‑file and low‑risk edits.
- Strong signals to delegate: cross‑file changes, research/pattern finding, scaffolding tests/tours, or multi‑stage tasks.
- Roles (see `.claude/agents/`):
    - Archer — research/pattern finding; cites file paths/snippets; no edits.
    - Scout — test scaffolding per docs/style/TESTING.md; minimal tests; no production edits.
    - Odoo Engineer — minimal, focused implementation per docs/style/ODOO.md; propose diffs first.
    - Inspector — concise code‑quality/perf pass with a short fix list and file paths.
- Subagent output contract (return in main context): Decision • Evidence (paths/snippets) • Diffs/Paths • Next steps •
  Risks.
- Tool scope: grant only needed tools; default read‑only; enable write only for implementation steps.
- Model routing: use lightweight models for simple tasks; escalate only when acceptance criteria require deeper
  reasoning or larger context (don’t hardcode vendor model names in prompts).

Tooling Guidance

- Prefer `odoo-intelligence__*` for Odoo searches/updates; `docker__*` for container data.
- Use built‑ins (Read/Edit/Grep/Glob) when MCP doesn’t cover the need.
- Access container paths via tools, not host file ops.
 - Diff‑first for multi‑file changes: propose short plan + diffs, wait for approval.
 - Cite evidence with file paths and key line hints when asserting findings.

Testing Knowledge

- Use base classes and tags from docs/style/TESTING.md.
- Place Python tests under `addons/<module>/tests/` and JS/tours under `addons/<module>/static/tests/`.
- Tour selectors: simple CSS only; no jQuery pseudo‑selectors.

Security & Safety

- Respect access rules; avoid insecure defaults.
- Use `with_context(skip_shopify_sync=True)` when bulk updates or tests could trigger syncs.

See also

- docs/style/ODOO.md
- docs/style/TESTING.md
- docs/TOOL_SELECTION.md
- docs/system/AGENT_SAFEGUARDS.md
- docs/odoo18/API_PATTERNS.md
- docs/odoo18/SECURITY_PATTERNS.md
- docs/odoo18/PERFORMANCE_ORM.md
