# AGENTS.md — Codex CLI Operating Guide (Read Me First)

Treat this file as the launch checklist for every Codex session. Skim it, open the linked docs, then keep prompts lean.

## Start Here

- Use the documentation table of contents (`docs/README.md`) to grab handles instead of copying long excerpts.
- Before changing code, open the matching style page (`docs/style/python.md`, `docs/style/javascript.md`,
  `docs/style/testing.md`).
- Clarify your role expectations with the guides under `docs/roles/` (analyst, engineer, tester, reviewer, maintainer).
- Active migration doc: `docs/todo/NEW_ARCH.md` (living OPW/CM stack + addons
  plan).

## Project Snapshot

- Custom addons live under `./addons/`; host `./` maps to container `/volumes/`.
- We target Odoo 18 Enterprise. Never edit generated GraphQL artifacts (`services/shopify/gql/*`, `graphql/schema/*`).
- Always go through `uv run ...`; the Odoo environment must bootstrap every command (tests, scripts, shell helpers).
- Never call the system Python directly; use `uv run python ...` (or the scripted helpers) so the managed env stays in
  sync.
- Common helper entry points are defined in `[project.scripts]` inside `pyproject.toml` (examples: `test`, `test-plan`,
  `restore-from-upstream`). Prefer them over ad-hoc commands and suggest additions when a useful script is missing.
- GPT service users seed automatically during restores when `.env` defines `ODOO_KEY`; see
  `docs/tooling/gpt-service-user.md` for provisioning details and API key usage.
- When you need multi-line scratch code, save it under `tmp/scripts/` and run `uv run python tmp/scripts/<name>.py`
  so the `uv run` sandbox bypass applies and you can iterate without heredocs.

## Operating Guardrails

- Zero-warning + full-test acceptance gate: follow `docs/policies/acceptance-gate.md` and gate with
  `uv run test run --json`.
- Respect `docs/policies/coding-standards.md` and `docs/policies/doc-style.md` for naming, formatting, and docs-as-code.
- Update relevant docs in the same change when behavior shifts; link handles rather than pasting large snippets.
- Preserve history (`git mv`, minimal diffs) and avoid destructive git actions unless the operator explicitly directs
  them.

## Workflow Loop

- The working loop (plan → patch → inspect → targeted tests → iterate → gate) is spelled out in
  `docs/workflows/codex-workflow.md`.
- Use `docs/workflows/testing-workflow.md` and `docs/testing.md` to scope and shard tests via JSON summaries.
- Large refactors, migrations, debugging, or performance work each have their own playbooks under `docs/workflows/`—open
  the relevant one before diving in.

## Testing & Scripts

- Reuse the scripted helpers in `pyproject.toml` to run tests, lint, or maintenance tasks (e.g., `uv run test unit`,
  `uv run test plan --phase all`).
- `docs/testing.md` summarizes the recommended commands and filtering flags; `docs/tooling/testing-cli.md` documents
  detached mode, sharding, and JSON outputs.
- Python formatting and linting commands live in `docs/style/python.md`; JS/Owl specifics live in
  `docs/style/javascript.md` and `docs/style/hoot-testing.md`.

## Tooling Order

- Prefer Odoo Intelligence MCP calls for model/field discovery, code search, or module updates before falling back to
  ad-hoc shell commands (`docs/tooling/odoo-intelligence.md`).
- Mirror the design style and patterns already established in `addons/product_connect/`; align new modules and views
  with that reference before inventing new approaches.
- Run JetBrains inspections on changed scope and then git scope before the gate (`docs/tooling/inspection.md`).
- Use Codex built-ins for routine file reads/searches and `apply_patch`; reserve JetBrains automation for IDE-only
  tasks.
- Sandbox/approval profiles, Codex Cloud setup, and maintenance scripts are documented in `docs/tooling/codex-cli.md`
  and `tools/codex_cloud/setup.sh`.

## Domain Notes

- **Odoo core**: Batch ORM operations, respect security defaults, and stay within container paths. Review
  `docs/odoo/orm.md`, `docs/odoo/security.md`, `docs/odoo/performance.md`, and `docs/odoo/workflow.md` before touching
  models or access rules. Use `with_context(skip_shopify_sync=True)` when bulk operations risk syncing loops.
- **Frontend & Tours**: Keep selectors simple and avoid jQuery-style filters. See `docs/style/owl-components.md`,
  `docs/style/playwright-patterns.md`, `docs/style/playwright-selectors.md`, and `docs/style/tour-debugging.md`.
- **Integrations**: Shopify and GraphQL patterns live in `docs/integrations/`; service mocking is covered in
  `docs/references/service-mocking.md`. Generated files stay untouched.

## Addons & External Code

- Addons live directly in this repo under `./addons/` (no submodules). If an addon needs to be shared
  externally, mirror or export it from this repo instead of embedding a submodule.
- Compose already maps host `./addons` to `/volumes/addons`; no extra container wiring required.

## Research & Citations

- Use web search when information may have changed (APIs, pricing, releases) or when you need citations. Default to
  primary sources.
- Cite unstable facts inline using the Codex CLI citation format; never drop raw URLs in summaries.

## Reference Handles You’ll Reuse

- Architecture: `docs/architecture.md`, `docs/resources.md`
- Testing patterns & advanced topics: `docs/style/testing.md`, `docs/style/testing-advanced.md`,
  `docs/references/test-templates.md`
- Performance & bulk operations: `docs/workflows/performance-review.md`, `docs/workflows/bulk-operations.md`
- Planning & estimation: `docs/workflows/planning.md`
- Environment utilities: `docker/scripts/restore_from_upstream.py`, `tools/codex_cloud/setup.sh`

Keep AGENTS.md thin: route deeper guidance to the linked pages so we maintain a single, accurate source of truth.
