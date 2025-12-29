---
name: testing-gate-run
description: Use when running or gating tests; standardizes uv run commands and JSON checks.
---

# Testing Gate Run

## Scope

- This skill covers running, scoping, and gating tests with `uv run`.
- For writing tests, use $test-authoring.

## Rules

- Always use `uv run`; never call system Python directly.
- Prefer `[project.scripts]` entry points from `pyproject.toml`.
- Gate on JSON summaries and require `success: true`.

## Fast loop

- Unit loop: `uv run test unit --modules <touched>`.
- JS loop: `uv run test js --js-modules <touched>`.
- Integration loop: `uv run test integration --integration-modules <touched>`.
- Tour loop: `uv run test tour --tour-modules <touched>`.

## Gate and summaries

- Full gate: `uv run test run --json`.
- Check `tmp/test-logs/latest/summary.json` for `success: true`.
- Optional: `uv run test validate --json` for summary consistency.

## Detached runs

- Start: `TEST_DETACHED=1 uv run test run --json`.
- Wait: `uv run test wait --json`.

## Other helpers

- `uv run test plan --phase all` to preview sharding.
- `JS_COUNT_STRATEGY=runtime` for executed Hoot counts.

## References

- @docs/TESTING.md
- @docs/tooling/testing-cli.md
- @docs/workflows/testing-workflow.md
