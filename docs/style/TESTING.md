# Testing Style

Basics

- Place Python tests under `addons/<module>/tests/` and JS/tours under `addons/<module>/static/tests/`.
- Use base classes and factory helpers; avoid ad‑hoc data creation where possible.
- Tag tests appropriately (unit/integration/tour) to keep runs predictable.

Selectors (tours)

- Prefer simple, stable selectors (role/name) and avoid brittle CSS chains.
- Add explicit waits for UI state rather than fixed sleeps.

See also

- Advanced: [style/testing-advanced.md](testing-advanced.md)
- Workflow: [../workflows/testing-workflow.md](../workflows/testing-workflow.md)

LLM‑Friendly Results

- Always gate on JSON: parse `tmp/test-logs/latest/summary.json` and require `success: true`.
- For long tours, run detached and wait: `TEST_DETACHED=1 uv run test run --json` then `uv run test wait --json`.
- JS totals: by default count definitions (number of `test(...)`). Set `JS_COUNT_STRATEGY=runtime` to report executed
  Hoot totals.
