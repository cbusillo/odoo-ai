---
title: Testing
---


Purpose

- Use the unified test CLI via `uv run`. Keep inner loops fast, then close with
  the full gate.

When

- During development loops and before merge gate.

Sources of Truth

- Patterns & fixtures: [style/testing.md](style/testing.md)
- Commands and flags: [tooling/testing-cli.md](tooling/testing-cli.md)
- Inspection workflow and zero-warning expectations:
  [tooling/inspection.md](tooling/inspection.md)

Commands

- Loop: `uv run test unit --modules <touched>`; JS with `--js-modules`;
  selective integration/tour as needed.
- Gate: `uv run test run --json` all phases; require `success: true`.
- Deterministic gate profile: `TESTKIT_PROFILE=gate uv run test run --json`
  when you need reproducible local gate behavior.
- Stack selection: `--stack opw|cm` (or
  `--env-file .platform/env/<context>.<instance>.env`) to load the correct
  local stack env before running tests.
  Stack/env-file selection is required. Stack-based runs fail closed when the
  runtime env file is missing; generate it first with
  `uv run platform select --context <context> --instance <instance>`.
- The canonical command list lives in
  [docs/tooling/testing-cli.md](tooling/testing-cli.md). Prefer those helpers
  over ad-hoc invocations.
- Scoped runs use `--modules` (or per-phase equivalents such as
  `--unit-modules`); treat `[project.scripts]` in `pyproject.toml` as the source
  of truth for available shortcuts.

Workflow Priority

- In Odoo-facing test refactors, treat PyCharm inspection as more authoritative
  than Ruff for deciding whether the resulting structure is acceptable.
- A normal inner loop is: patch -> inspection on changed scope -> targeted test
  run -> Ruff on touched files -> iterate.
- When an addon needs a shared Python test surface, prefer the `common`
  object pattern from [style/testing.md](style/testing.md) instead of broad
  wrapper modules.
- Use Ruff for fast style/syntax feedback, but do not stop when Ruff is clean
  if inspection still reports unresolved references, dynamic typing noise, or
  addon-test structure problems.

Notes

- Parse `tmp/test-logs/latest/summary.json` (or phase-specific summaries); wait
  for `success: true` before declaring a run green.
- Phase timeouts are defined under `[tool.odoo-test.timeouts]` in
  `pyproject.toml` and are enforced as hard shard kill limits.
- The runner preflight validates test structure (missing tags/`__init__.py`) and
  removes exited `testkit-*` containers before starting shards.
- Unit/JS phases build a per-session template DB (union of phase modules) and
  clone shards from it to avoid repeated module installs; template logs land
  under `tmp/test-logs/<session>/<phase>/template-*.log`.
- Use detached mode (`uv run test run --detached`, then `uv run test wait
  --json`) when long tours or integrations risk timeouts.
- The prod gate runs `uv run test run --json --stack <target>` so the correct
  local runtime env is applied. Platform code-gate commands automatically
  set `TESTKIT_PROFILE=gate`.
