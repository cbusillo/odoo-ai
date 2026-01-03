---
title: Testing
---


Purpose

- Use the unified test CLI via `uv run`. Keep inner loops fast, then close with
  the full gate.

## Flow (Fast -> Full)

- Loop: `uv run test unit --modules <touched>`; JS with `--js-modules`;
  selective integration/tour as needed.
- Gate: `uv run test run --json` all phases; require `success: true`.

## Pointers

- Patterns & fixtures: [style/testing.md](style/testing.md)
- Commands and flags: [tooling/testing-cli.md](tooling/testing-cli.md)

## Commands

- The canonical command list (phase entry points, detached mode, JSON output)
  lives in [docs/tooling/testing-cli.md](tooling/testing-cli.md). Prefer those
  helpers over ad-hoc invocations.
- Scoped runs use `--modules` (or per-phase equivalents such as
  `--unit-modules`); treat `[project.scripts]` in `pyproject.toml` as the source
  of truth for available shortcuts.

## Summaries

- Parse `tmp/test-logs/latest/summary.json` (or per-phase summaries) for a
  single result.

## Gate on JSON

- Parsing `tmp/test-logs/latest/summary.json` (or phase-specific summaries) is
  mandatory; wait for `success: true` before declaring a run green.
- Use detached mode (`uv run test run --detached`, then `uv run test wait
  --json`) when long tours or integrations risk timeouts.
