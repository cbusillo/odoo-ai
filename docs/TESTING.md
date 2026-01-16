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

Commands

- Loop: `uv run test unit --modules <touched>`; JS with `--js-modules`;
  selective integration/tour as needed.
- Gate: `uv run test run --json` all phases; require `success: true`.
- Stack selection: `--stack opw|cm` (or
  `--env-file docker/config/<stack>-local.env`) to load the correct local
  stack env before running tests. If a `*-test-local` stack exists (for example
  `cm-test-local`), `--stack cm` uses it by default so tests do not interrupt
  dev stacks. Use `--stack cm-local` to target the dev stack explicitly.
  Stack/env-file selection is required for test runs.

- The canonical command list (phase entry points, detached mode, JSON output)
  lives in [docs/tooling/testing-cli.md](tooling/testing-cli.md). Prefer those
  helpers over ad-hoc invocations.
- Scoped runs use `--modules` (or per-phase equivalents such as
  `--unit-modules`); treat `[project.scripts]` in `pyproject.toml` as the source
  of truth for available shortcuts.

Notes

- Parse `tmp/test-logs/latest/summary.json` (or phase-specific summaries); wait
  for `success: true` before declaring a run green.
- Use detached mode (`uv run test run --detached`, then `uv run test wait
  --json`) when long tours or integrations risk timeouts.
- The prod gate runs `uv run test run --json --stack <target>` so the correct
  local stack env file is applied.
