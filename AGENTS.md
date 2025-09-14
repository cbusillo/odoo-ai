# AGENTS.md — Codex CLI Operating Guide (Read Me First)

This project is optimized for Codex CLI. Follow these rules to work fast, safely, and in the house style. Prefer
project MCP tools (Inspection, Odoo, Docker) where appropriate and validate with our test commands.

## Read Order (Before You Start)

- ToC: docs/README.md
- Policies: docs/policies/coding-standards.md
- Style: docs/style/python.md, docs/style/javascript.md, docs/style/testing.md
- Odoo canon: docs/odoo/orm.md, docs/odoo/security.md, docs/odoo/performance.md, docs/odoo/workflow.md
- Workflows: docs/workflows/codex-workflow.md, docs/workflows/odoo-development.md, docs/workflows/testing-workflow.md
  and docs/workflows/refactor-workflows.md, docs/workflows/debugging.md
- Policies: docs/policies/acceptance-gate.md, docs/policies/coding-standards.md, docs/policies/doc-style.md
- Tooling: docs/tooling/codex-cli.md, docs/tooling/testing-cli.md, docs/tooling/inspection.md,
  docs/tooling/odoo-intelligence.md

When implementing a feature, skim the most relevant style doc right before coding (Python, JS, or Odoo) and the Testing
doc before writing or updating tests.

## Project Facts

- Custom addons: `./addons/`
- Odoo version: 18 Enterprise
- Do not modify: `services/shopify/gql/*`, `graphql/schema/*`
- Container mapping: host `./` → container `/volumes/`
- Never run Python directly: use the Odoo environment and `uv run` tasks

## Critical Rules

- Tools: Prefer project tools (Inspection, Odoo Intelligence) and keep docs policy‑level.
- Git: Use `git mv` to preserve history
- Tests: Use only `uv run` commands below. Preferred single-call gate: `uv run test run --json`.
- Formatting: Use Ruff for Python; Owl.js patterns and no semicolons for JS
- Python line length: 133 characters max
- Docs-as-code: When you change behavior, update relevant docs (and fix inaccuracies) in the same PR. Small improvements
  are welcome.

## Acceptance Gate (Zero‑Warning)

- Do not mark a task complete until BOTH are true:
    - Targeted tests pass via `uv run test-*` for the touched module(s), and
    - MCP inspection reports 0 errors, warnings, weak_warnings, and infos for the touched files.
- If a finding is a true false positive, add a narrowly targeted `noinspection` with a one‑line justification and a
  reference link. Never add blanket or broad suppressions.
- If the Inspection MCP is unavailable, state that explicitly and treat inspection as blocking unless the operator
  accepts a justified exception.

## Commands

```bash
# Testing (unified CLI)
uv run test run           # Run all phases with parallel sharding
  - Add --detached to run in background and use `uv run test wait --json` to gate
uv run test unit          # Unit tests (sharded)
uv run test js            # JS/hoot tests (sharded)
uv run test integration   # Integration tests (optional sharding)
uv run test tour          # Browser/UI tours (optional sharding)
uv run test clean         # Drop test DBs/filestores and artifacts
uv run test plan --phase all  # Print sharding plan (JSON)
uv run test doctor           # Environment diagnostics (Docker, DB, disk)
  - Filters: add `--modules m1,m2` and/or `--exclude x,y` to scope phases. Works with `test run` and `test plan`.
  - Per-phase filters: `--unit-modules/--unit-exclude`, `--js-modules/--js-exclude`, `--integration-modules/--integration-exclude`, `--tour-modules/--tour-exclude`.
  - Add --json to print a single bottom-line JSON payload and exit 0/1
  - Sharding flags: --unit-shards N, --js-shards N, --integration-shards N, --tour-shards N

# Code Quality
uv run ruff format .      # Format Python
uv run ruff check --fix   # Fix Python issues
```

## CLI Sanity Checks (Codex)

- Quick non-interactive check (read-only):
    - `codex exec --sandbox read-only "Reply with exactly: ok"`

Notes

- Model selection: omit `--model` to use the CLI default. Override via env only when a task requires it (e.g., large
  context).

## Codex Workflow (Entry Point)

- Working loop: docs/workflows/codex-workflow.md
- Style & Testing: docs/style/*
- Odoo canon: docs/odoo/*

## Extra Addons as Submodules (Operator Rule)

- When introducing external addons, add them as Git submodules:
    - `git submodule add <repo-url> addons/<addon_name>`
    - Commit `.gitmodules` and the submodule path
- Compose already mounts `./addons` to `/volumes/addons`; no extra mapping needed.
- For submodule changes, prefer opening a PR in the submodule repo; avoid committing generated files here.

## Tests (How-To Docs)

## Codex CLI Operating Rules

- Planning: Use the plan tool; update as you proceed.
- Preambles: Before grouped tool calls, send a one‑sentence preamble describing what you are about to do.
- File edits: Use `apply_patch` with minimal, focused changes; prefer editing existing files over creating new ones.
- Validation: Prefer `uv run test run --json` to run/wait/gate in one call; expand scope only after green.
    - If running targeted phases, read JSON summaries, not terminal tails. See “LLM‑Friendly Results” in
      docs/style/testing.md. Parse `tmp/test-logs/latest/summary.json` and require `success: true`.
    - Test counts: JS totals default to definition counts (number of `test(...)` in `*.test.js`). Set
      `JS_COUNT_STRATEGY=runtime` to report executed Hoot totals.
    - Pointers: `tmp/test-logs/current` points to the in‑progress session; `tmp/test-logs/latest` points to the last
      completed session.
    - Long tours: you may enable detached mode to avoid agent timeouts by setting `TEST_DETACHED=1`.
      Logs and summaries are still written under `tmp/test-logs/`.
- Brevity: Default to concise, structured updates; avoid filler. Prefer bullets with bolded keywords.
- Shell & IO: Prefer built‑in tools for routine work. Use `rg` via the built‑in shell (or built‑in file ops) for
  reads/search/listing, and `apply_patch` for edits. Use JetBrains/IDE tools only for IDE‑specific actions (inspections,
  rename refactors, symbol info), not for routine file IO.

## Tooling Priority (Fast Path)

- odoo-intelligence first: Prefer `odoo-intelligence__*` for Odoo queries, code search/analysis, and module updates. Use
  other MCP tools like `docker__*` when appropriate.
- Inspections second: Use `inspection-pycharm__*` to surface code problems and navigate findings before any ad‑hoc
  scans.
- Built‑ins third: Use built‑in file ops and the built‑in shell for reads/edits and targeted commands. Do not use shell
  for basic find/grep/cat/ls — use file ops or `rg` via built‑ins instead.
- JetBrains last: Use `jetbrains__*` only when an IDE‑specific action is required (e.g., open editor view, IDE
  refactors, run configurations).

## Web Search

- Use web search when information could have changed (APIs, docs, prices, laws), when you need citations, or when you
  are unsure.

Add citations for any unstable facts or external claims. Prefer primary documentation over blogs.

## Odoo‑Specific Rules (Must Follow)

- Paths: Use container paths inside tools (`/volumes/addons/*`, `/volumes/enterprise/*`); never reference `/odoo/*` on
  host.
- Execution: Never run Python directly; use Odoo environment commands and `uv run` test tasks.
- Use the odoo-intelligence MCP when possible
- Context flags: Use `with_context(skip_shopify_sync=True)` to avoid sync loops when appropriate.

See docs/odoo/workflow.md for details and container rules. It’s important to respect the style rules.

## Odoo Canon (Consult Before Coding)

- APIs and ORM: docs/odoo/orm.md
- Security: docs/odoo/security.md
- Performance & batching: docs/odoo/performance.md

Skim these before: adding fields/methods, writing constraints/onchanges, batch writes/importers, computed fields, and
access rules.

## Language Style Snapshots

- Python: Type hints everywhere (explicit `-> None` when applicable), f‑strings only, early returns allowed; see
  docs/style/python.md.
- JavaScript: Owl.js 2.0, ES modules, no semicolons, simple selectors for tours; see docs/style/javascript.md.

## Testing Rules (Start Here)

- Use base classes and tags from docs/style/testing.md to avoid SKU validation pitfalls and brittle tours.
- Place tests under `tests/` (Python) and `static/tests/` (JS, tours) following naming patterns.
- For tour tests: only simple CSS selectors; no jQuery patterns like `:visible` or `:contains()`.

Related patterns and templates:

- Playwright selectors: docs/style/playwright-selectors.md
- Playwright patterns & debugging: docs/style/playwright-patterns.md, docs/style/tour-debugging.md
- Test templates and mocking: docs/references/test-templates.md, docs/references/service-mocking.md

## Large/Complex Workflows

- Thresholds: 5+ files or multi‑phase work → break into clear plan steps

## Typical Workflow

1) Discover: Skim the relevant style doc(s) and module layout.
2) Plan: Write a short plan with the plan tool; confirm scope.
3) Implement: Use `apply_patch` with surgical diffs; keep changes minimal.
4) Validate: Run `uv run` tests for the touched area; fix fast.
5) Format: `uv run ruff format .` and `uv run ruff check --fix`.
6) Summarize: Report what changed and what to do next.

## References You Will Use Often

- Odoo canon and workflow: docs/odoo/*, docs/workflows/odoo-development.md, docs/architecture.md
- Testing patterns: docs/style/testing.md

## Recipes

- Run targeted tests:
    - `uv run test unit`
    - `uv run test integration`
    - `uv run test tour`
    - See docs/tooling/testing-cli.md for scoping flags and JSON summaries.

## New Addon Happy Path

1) Scaffold minimal addon (manifest, init) and access rules early.
2) Add smallest model or extension with a single field/compute.
    - Update `models/__init__.py` to import new files; verify field registration in `_fields`.
3) Write minimal tests with Scout (fixtures, factories, a passing unit).
4) Add views/data; keep security in place; re‑run targeted tests.
5) If integration needed, add service skeleton and mocks; avoid secrets.
6) Iterate with Inspector → Refactor for quality/perf fixes.

References: docs/style/testing.md, docs/references/test-templates.md, addons/README.md.

## Tours & Frontend (Owl)

- Keep selectors simple (no jQuery‑style). See: docs/style/playwright-selectors.md.
- Follow Owl patterns and troubleshooting: docs/style/owl-troubleshooting.md.
- Use Playwright patterns & debugging: docs/style/playwright-patterns.md,
  docs/style/tour-debugging.md.

## Integrations (Shopify)

- Read: docs/integrations/shopify-sync.md, docs/integrations/graphql.md, docs/integrations/webhooks.md.
- Service mocking patterns: docs/references/service-mocking.md.
- Use `with_context(skip_shopify_sync=True)` for imports/bulk updates/test data.
- Do not edit generated files: `services/shopify/gql/*`, `graphql/schema/*`.

## Project Health

Keep this document as your operating baseline. When in doubt, re‑read the relevant style doc before coding and prefer
MCP tools to keep iterations fast and reliable.
