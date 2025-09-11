# Codex Workflow (No Subagents)

Purpose

- Make Codex runs consistent with our house rules so tasks are repeatable, non‑interactive, and converge to zero
  warnings.

Execution Norms

- File edits: Prefer structured edits (Edit/Write). If the session cannot approve edits, fall back to Bash here‑docs to
  write files.
- Tests: Prefer `uv run test-gate --json` to run/wait and gate in one call. For targeted phases, still use
  `uv run test-*` and read JSON summaries.
- Inspection: Use the Inspection MCP (if available) to lint/inspect dynamic Odoo types and fix issues; rerun until
  clean.
- Zero‑Warning Policy: Treat inspection warnings (warning, weak_warning, info) as failures; fix them or add a narrowly
  targeted `noinspection` with a one‑line justification for true false positives.

Acceptance Gate

- Do not declare completion until BOTH are true:
    - Tests gate green via `uv run test-gate` (exit 0) or targeted `uv run test-*` with JSON summary success, and
    - MCP inspection reports 0 errors, warnings, weak_warnings, and infos for the touched files.
- If the Inspection MCP is not available, call this out explicitly and treat inspection as blocking unless the operator
  agrees to a narrowly justified exception.

Odoo 18 Canon & Local Examples

- Odoo 18: `docs/odoo18/API_PATTERNS.md`, `docs/odoo18/SECURITY_PATTERNS.md`, `docs/odoo18/PERFORMANCE_ORM.md`
- Examples: `addons/product_connect/`, `addons/external_ids/`

Typical Definition of Done (DoD)

- Tests pass (e.g., `uv run test-unit addons/<module>`)
- MCP inspection clean (0 errors/warnings/weak_warnings/infos) on touched files
- Adheres to Odoo 18 checklist for fields/compute/views

How to Run

- Create a task file from the template describing the goal and DoD (e.g., `tmp/codex-tasks/feature.md`).
- Run Codex directly:
  -
  `codex exec --sandbox workspace-write --allowed-tools "Bash Edit Write mcp__inspection-pycharm__inspection_trigger mcp__inspection-pycharm__inspection_get_status mcp__inspection-pycharm__inspection_get_problems" "Execute the task in @tmp/codex-tasks/feature.md. Follow project rules in AGENTS.md and docs/codex/WORKFLOW.md. Apply changes and run tests (uv run). Use Inspection MCP if available and converge to zero warnings. Return a concise report." | tee tmp/codex-runs/$(date +%Y%m%d_%H%M%S).txt`
- Inspect transcript with simple greps:
    - `rg -n "addons/|uv run test-|inspection-pycharm__" tmp/codex-runs/*.txt | tail -n 200`

Test Results (LLM‑friendly)

- Do not rely on terminal tails/heads. Simplest path: `uv run test-gate --json` (exits 0/1 and prints a single JSON
  payload). While a run is active, `tmp/test-logs/current` points to the in‑progress session; after completion, use
  `tmp/test-logs/latest/summary.json` (or per‑phase `all.summary.json`).
- Treat `success: true` as the only passing signal; otherwise, iterate and rerun.
