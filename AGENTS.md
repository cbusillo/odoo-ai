# AGENTS.md — Codex CLI Operating Guide (Read Me First)

This project is optimized for Codex CLI. Follow these rules to work fast, safely, and in the house style. Always prefer
MCP tools, keep plans tight, and validate with our test commands.

## Read Order (Before You Start)

- Core rules: docs/style/CORE.md
- Language/style: docs/style/PYTHON.md, docs/style/JAVASCRIPT.md
- Odoo patterns: docs/style/ODOO.md, docs/ODOO_WORKFLOW.md
- Testing: docs/style/TESTING.md, docs/odoo18/TESTING_ADVANCED.md
    - See “Runner & Logs” section in docs/style/TESTING.md
- Odoo 18 canon: docs/odoo18/API_PATTERNS.md, docs/odoo18/SECURITY_PATTERNS.md, docs/odoo18/PERFORMANCE_ORM.md
- Tooling strategy: docs/TOOL_SELECTION.md, docs/system/AGENT_SAFEGUARDS.md, docs/system/ERROR_RECOVERY.md,
  docs/system/MODEL_SELECTION.md
- Agents overview: docs/agents/README.md (then specific agents under docs/agents/*.md)
- Patterns library: docs/agent-patterns/*, docs/references/*
- Codex specifics: docs/CODEX_CONFIG.md, docs/codex/reference.md, docs/codex/usage.md, docs/codex/advanced.md,
  docs/system/CODEX_MCP_REFERENCE.md

When implementing a feature, skim the most relevant style doc right before coding (Python, JS, or Odoo) and the Testing
doc before writing or updating tests.

## Project Facts

- Custom addons: `./addons/`
- Odoo version: 18 Enterprise
- Do not modify: `services/shopify/gql/*`, `graphql/schema/*`
- Container mapping: host `./` → container `/volumes/`
- Never run Python directly: use the Odoo environment and `uv run` tasks

## Critical Rules

- Tools: ALWAYS favor MCP tools over Bash (10–100x faster); see docs/TOOL_SELECTION.md
- Git: Use `git mv` to preserve history
- Tests: Use only `uv run` commands below
- Formatting: Use Ruff for Python; Owl.js patterns and no semicolons for JS
- Python line length: 133 characters max

## Commands

```bash
# Testing
uv run test-unit          # Unit tests
uv run test-integration   # Integration tests
uv run test-tour          # Browser/UI tests
uv run test-js            # JS/hoot and browser_js tests
uv run test-all           # Full test suite
uv run test-clean         # Drop test DBs/filestores and artifacts

# Code Quality
uv run ruff format .      # Format Python
uv run ruff check --fix   # Fix Python issues
```

## Codex CLI Operating Rules

- Planning: Use the plan tool to outline 3–6 concise steps; keep exactly one step in_progress; update as you proceed.
- Preambles: Before grouped tool calls, send a one‑sentence preamble describing what you are about to do.
- File edits: Use `apply_patch` with minimal, focused changes; prefer editing existing files over creating new ones.
- Validation: Run targeted tests for what you changed; expand scope only after green.
- Brevity: Default to concise, structured updates; avoid filler. Prefer bullets with bolded keywords.

## Delegation & Safeguards (Must Know)

- Thresholds: 3–5 files → consider specialists; 5+ files → delegate to a sub‑agent; 20+ files → must use a sub‑agent.
- Never delegate to the same agent type (no self‑calls) to avoid recursion; see docs/system/AGENT_SAFEGUARDS.md.
- Use GPT agent for verification when information is unstable, cross‑checking external docs; see
  docs/system/MODEL_SELECTION.md.

## Tooling Priority (Fast Path)

- MCP first: Use specialized `mcp__odoo-intelligence__*`, `mcp__docker__*`, and other MCP tools where available.
- Built‑ins next: Use file ops (Read/Write/Edit/Glob/Grep) when MCP doesn’t cover it.
- Bash last: Only when neither MCP nor built‑ins suffice; document why. See docs/TOOL_SELECTION.md.

## Agents Shortlist (When To Use Which)

- Archer (docs/agents/archer.md): Codebase research, pattern finding across modules.
- Scout (docs/agents/scout.md): Test scaffolding, fixtures, data factories, tour shells.
- Inspector (docs/agents/inspector.md): Code quality, perf, security checks across repo.
- Refactor (docs/agents/refactor.md): Systematic, multi‑file changes after Inspector findings.
- Owl (docs/agents/owl.md): Frontend (Owl.js 2.0), components, tours.
- Dock (docs/agents/dock.md): Container ops (restart, logs, env), module updates.
- Debugger (docs/agents/debugger.md): Repro, logs, bisect, failure isolation.
- Phoenix (docs/agents/phoenix.md): Version/migration flows, upgrade hooks.
- QC (docs/agents/qc.md): End‑to‑end quality pipeline orchestration.

Rule of thumb: If scope ≥ 5 files, or you need parallel specialized work, launch the appropriate agent instead of
expanding main context.

## Web Search

- Enable in `~/.codex/config.toml`:
    - `[tools]` → `web_search = true`
    - `[sandbox_workspace_write]` → `network_access = true`
- Use web search when information could have changed (APIs, docs, prices, laws), when you need citations, or when you
  are unsure.

Add citations for any unstable facts or external claims. Prefer primary documentation over blogs.

## Odoo‑Specific Rules (Must Follow)

- Paths: Use container paths inside tools (`/volumes/addons/*`, `/volumes/enterprise/*`); never reference `/odoo/*` on
  host.
- Execution: Never run Python directly; use Odoo environment commands and `uv run` test tasks.
- Context flags: Use `with_context(skip_shopify_sync=True)` to avoid sync loops when appropriate.
- Field naming: Prefer `carrier` over `carrier_id` when the field returns a recordset (Odoo 18 pattern); follow existing
  module conventions.
- Don’t touch generated files: `services/shopify/gql/*`, `graphql/schema/*`.

See docs/style/ODOO.md for details and container rules.

## Odoo 18 Canon (Consult Before Coding)

- APIs and ORM: docs/odoo18/API_PATTERNS.md
- Security: docs/odoo18/SECURITY_PATTERNS.md
- Performance & batching: docs/odoo18/PERFORMANCE_ORM.md

Skim these before: adding fields/methods, writing constraints/onchanges, batch writes/importers, computed fields, and
access rules.

## Language Style Snapshots

- Python: Type hints everywhere (explicit `-> None` when applicable), f‑strings only, early returns allowed; see
  docs/style/PYTHON.md.
- JavaScript: Owl.js 2.0, ES modules, no semicolons, simple selectors for tours; see docs/style/JAVASCRIPT.md.

## Testing Rules (Start Here)

- Use base classes and tags from docs/style/TESTING.md to avoid SKU validation pitfalls and brittle tours.
- Place tests under `tests/` (Python) and `static/tests/` (JS, tours) following naming patterns.
- For tour tests: only simple CSS selectors; no jQuery patterns like `:visible` or `:contains()`.

Related patterns and templates:

- Playwright selectors: docs/agent-patterns/playwright-selectors.md
- Playwright patterns & debugging: docs/agent-patterns/playwright-patterns.md, docs/agent-patterns/tour-debugging.md
- Test templates and mocking: docs/agent-patterns/test-templates.md, docs/references/service-mocking.md

## Large/Complex Workflows

- Thresholds: 5+ files or multi‑phase work → break into clear plan steps; use sessions when delegating via Codex MCP;
  consult docs/system/AGENT_SAFEGUARDS.md.
- Error handling: Follow docs/system/ERROR_RECOVERY.md for retries, fallbacks, and rate‑limit handling.

When delegating: follow docs/system/AGENT_SAFEGUARDS.md for safe handoffs; agents must not call themselves.

## Typical Workflow

1) Discover: Skim the relevant style doc(s) and module layout.
2) Plan: Write a short plan with the plan tool; confirm scope.
3) Implement: Use `apply_patch` with surgical diffs; keep changes minimal.
4) Validate: Run `uv run` tests for the touched area; fix fast.
5) Format: `uv run ruff format .` and `uv run ruff check --fix`.
6) Summarize: Report what changed and what to do next.

## References You Will Use Often

- Odoo patterns and workflow: docs/style/ODOO.md, docs/ODOO_WORKFLOW.md
- Testing patterns: docs/style/TESTING.md, docs/odoo18/TESTING_ADVANCED.md
- Tool selection and speed: docs/TOOL_SELECTION.md
- Codex configuration and MCP details: docs/CODEX_CONFIG.md, docs/codex/reference.md, docs/codex/usage.md,
  docs/codex/advanced.md, docs/system/CODEX_MCP_REFERENCE.md

## MCP Recipes (Copy/Paste Starters)

- List models/fields quickly:
    - `mcp__odoo-intelligence__model_query(operation="list", pattern="product.*")`
    - `mcp__odoo-intelligence__field_query(model_name="product.template", operation="list")`
- Find overrides/patterns:
    - `mcp__odoo-intelligence__search_code(pattern="def create\(", file_type="py")`
    - `mcp__odoo-intelligence__analysis_query(analysis_type="inheritance", model_name="product.template")`
- Run targeted tests:
    - `uv run test-unit addons/<module>`
    - `uv run test-integration addons/<module>`
    - `uv run test-tour addons/<module>`
- Update a module in proper env:
    - `mcp__odoo-intelligence__odoo_update_module(modules="<module>")`

Prefer MCP over Bash; only fall back to Bash if a needed flag isn’t supported (document why).

## New Addon Happy Path

1) Scaffold minimal addon (manifest, init) and access rules early.
2) Add smallest model or extension with a single field/compute.
3) Write minimal tests with Scout (fixtures, factories, a passing unit).
4) Add views/data; keep security in place; re‑run targeted tests.
5) If integration needed, add service skeleton and mocks; avoid secrets.
6) Iterate with Inspector → Refactor for quality/perf fixes.

References: docs/style/TESTING.md, docs/agent-patterns/test-templates.md, addons/README.md.

## Tours & Frontend (Owl)

- Keep selectors simple (no jQuery‑style). See: docs/agent-patterns/playwright-selectors.md.
- Follow Owl patterns and troubleshooting: docs/agent-patterns/owl-troubleshooting.md.
- Use Playwright patterns & debugging: docs/agent-patterns/playwright-patterns.md,
  docs/agent-patterns/tour-debugging.md.

## Integrations (Shopify)

- Read: docs/integrations/shopify.md, docs/agent-patterns/graphql-patterns.md, docs/agent-patterns/webhook-patterns.md.
- Service mocking patterns: docs/references/service-mocking.md.
- Use `with_context(skip_shopify_sync=True)` for imports/bulk updates/test data.
- Do not edit generated files: `services/shopify/gql/*`, `graphql/schema/*`.

## Model Selection & Verification

- Choose the right model/tool for the task; see docs/system/MODEL_SELECTION.md.
- For unstable facts or external dependencies, verify with GPT or web search and cite sources.

## Project Health

- Known issues, flakiness, and status: docs/status/TEST_STATUS.md.

Keep this document as your operating baseline. When in doubt, re‑read the relevant style doc before coding and prefer
MCP tools to keep iterations fast and reliable.
