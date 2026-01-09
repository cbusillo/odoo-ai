# AGENTS.md — Codex CLI Operating Guide (Read Me First)

Treat this file as the launch checklist for every Codex session. Skim it, open
the linked docs, then keep prompts lean.

## Start Here

- Use the documentation table of contents (`docs/README.md`) to grab handles
  instead of copying long excerpts.
- Before changing code, open the matching style page (`docs/style/python.md`, `docs/style/javascript.md`,
  `docs/style/testing.md`).
- Clarify your role expectations with @docs/roles.md (analyst, engineer,
  tester, reviewer, maintainer).

## Project Snapshot

- Custom addons live under `./addons/`; host `./` maps to container `/volumes/`.
- We target Odoo 19 Enterprise. Never edit generated GraphQL artifacts
  (`addons/product_connect/services/shopify/gql/*`,
  `addons/product_connect/graphql/schema/*`).
- Always go through `uv run ...`; the Odoo environment must bootstrap every
  command (tests, scripts, shell helpers).
- Never call the system Python directly; use `uv run python ...` (or the
  scripted helpers) so the managed env stays in sync.
- Common helper entry points are defined in `[project.scripts]` inside
  `pyproject.toml` (examples: `test`, `restore`). Prefer them over ad-hoc
  commands and suggest additions when a useful script is missing.
- GPT service users seed automatically during restores when `.env` defines
  `ODOO_KEY`; see `docs/tooling/gpt-service-user.md` for provisioning details
  and API key usage.
- When you need multi-line scratch code, save it under `tmp/scripts/` and run
  `uv run python tmp/scripts/<name>.py` so the `uv run` sandbox bypass applies
  and you can iterate without heredocs.

## Version Guardrails (Odoo 19 + Owl 2)

- Views: use `<list>` roots, not `<tree>`.
- Views: use `invisible`/`readonly`/`required` and `column_invisible`; avoid
  legacy `attrs`/`states`.
- Frontend: native ESM only (`@web/...`, `@odoo/...`); no `odoo.define`.
- Frontend: do not add `/** @odoo-module */` in new files.

## Operating Guardrails

- Zero-warning + full-test acceptance gate: follow
  `docs/policies/acceptance-gate.md` and gate with `uv run test run --json`.
- Respect `docs/policies/coding-standards.md` and
  `docs/policies/doc-style.md` for naming, formatting, and docs-as-code.
- Naming guardrail: avoid abbreviations and 1–2 letter locals (e.g., `idx`,
  `cfg`, `tmp`, `obj`, `val`, `res`, `ctx`). Allow only explicit, well-known
  tokens (`id`, `db`, `api`, `orm`, `env`, `io`, `url`, `ui`, `ux`, `ip`,
  `http`, `json`, `xml`, `sql`) and math-only contexts.
- Update relevant docs in the same change when behavior shifts; link handles
  rather than pasting large snippets.
- Preserve history (`git mv`, minimal diffs) and avoid destructive git actions
  unless the operator explicitly directs them.
- Keep branch/worktree hygiene per @docs/roles.md (clean up Code-created
  branches as you go).

## Workflow Loop

- The working loop (plan → patch → inspect → targeted tests → iterate → gate)
  is spelled out in `docs/workflows/codex-workflow.md`.
- Use `docs/TESTING.md` to scope and shard tests via JSON summaries.
- Large refactors, migrations, debugging, or performance work each have their
  own playbooks under `docs/workflows/`—open the relevant one before diving in.

## Proactive Improvements

- Proactively suggest small environment or tooling improvements when you notice
  friction (scripts, config, runtime baselines); keep suggestions brief and
  link to the relevant docs (e.g., `docs/tooling/ops.md`,
  `docs/tooling/runtime-baselines.md`, `docs/tooling/coolify.md`).
- Let the operator decide; don’t apply environment changes without explicit
  approval.
- If guidance is missing, suggest updates to the relevant docs instead of
  expanding AGENTS.md.

## Testing & Scripts

- Reuse the scripted helpers in `pyproject.toml` to run tests, lint, or
  maintenance tasks (e.g., `uv run test unit`, `uv run test plan --phase all`).
- `docs/TESTING.md` summarizes the recommended commands and filtering flags;
  `docs/tooling/testing-cli.md` documents detached mode, sharding, and JSON
  outputs.
- Python formatting and linting commands live in `docs/style/python.md`; JS/Owl
  specifics live in `docs/style/javascript.md` and `docs/style/testing.md`.

## Tooling Order

- Prefer Odoo Intelligence MCP calls for model/field discovery, code search, or
  module updates before falling back to ad-hoc shell commands
  (`docs/tooling/odoo-intelligence.md`).
- Mirror the design style and patterns already established in
  `addons/product_connect/`; align new modules and views with that reference
  before inventing new approaches.
- Run JetBrains inspections on changed scope and then git scope before the gate
  (`docs/tooling/inspection.md`).
- Use Codex built-ins for routine file reads/searches and `apply_patch`; reserve
  JetBrains automation for IDE-only tasks.
- Sandbox/approval profiles are documented in `docs/tooling/codex-cli.md`.

## Domain Notes

- **Odoo core**: Batch ORM operations, respect security defaults, and stay
  within container paths. Review `docs/odoo/orm.md`, `docs/odoo/security.md`,
  `docs/odoo/performance.md`, and `docs/odoo/workflow.md` before touching models
  or access rules. Use `with_context(skip_shopify_sync=True)` when bulk
  operations risk syncing loops.
- **Frontend & Tours**: Keep selectors simple and avoid jQuery-style filters. See
  `docs/style/javascript.md`, `docs/style/browser-automation.md`, and
  `docs/style/testing.md`.
- **Integrations**: Shopify and GraphQL patterns live in
  `docs/integrations/`; service mocking is covered in
  `docs/style/testing.md`. Generated files stay untouched.

## Addons & External Code

- Addons live directly in this repo under `./addons/` (no submodules). If an
  addon needs to be shared externally, mirror or export it from this repo
  instead of embedding a submodule.
- Compose already maps host `./addons` to `/volumes/addons`; no extra container
  wiring required.

## Research & Citations

- Use web search when information may have changed (APIs, pricing, releases) or
  when you need citations. Default to primary sources.
- Cite unstable facts inline using the Codex CLI citation format; never drop
  raw URLs in summaries.

## Reference Handles You’ll Reuse

- Architecture: `docs/ARCHITECTURE.md`, `docs/resources.md`
- Testing patterns & advanced topics: `docs/style/testing.md`,
  `docs/TESTING.md`
- Performance & bulk operations: `docs/odoo/performance.md`, `docs/odoo/orm.md`
- Planning & estimation: `docs/workflows/codex-workflow.md`
- Environment utilities: restore helpers in `tools/` (use `uv run restore`)

Keep AGENTS.md thin: route deeper guidance to the linked pages so we maintain a
single, accurate source of truth.
