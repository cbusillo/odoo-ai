Title: Testing

Use the unified test CLI via `uv run`. Keep inner loops fast, then close with the full gate.

## Pointers

- Patterns & fixtures: [style/testing.md](style/testing.md)
- Advanced scenarios: [style/testing-advanced.md](style/testing-advanced.md)
- Workflow details: [workflows/testing-workflow.md](workflows/testing-workflow.md)

## Commands

- The canonical command list (phase entry points, detached mode, JSON output) lives in
  [docs/tooling/testing-cli.md](tooling/testing-cli.md). Prefer those helpers over ad-hoc invocations.
- Scoped runs use `--modules` (or per-phase equivalents such as `--unit-modules`); treat `[project.scripts]` in
  `pyproject.toml` as the source of truth for available shortcuts.

## Gate on JSON

- Parsing `tmp/test-logs/latest/summary.json` (or phase-specific summaries) is mandatory; wait for `success: true`
  before declaring a run green.
- Use detached mode (`uv run test run --detached`, then `uv run test wait --json`) when long tours or integrations risk
  timeouts.
