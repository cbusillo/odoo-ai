Title: Test CLI (uv)

Commands

- uv run test run — all phases, parallel sharding; add --json for gate
- uv run test unit|js|integration|tour — phase‑scoped; use module filters

Scoping Flags

- --modules m1,m2; --unit-modules/--js-modules for per‑phase filters

Summaries

- Read `tmp/test-logs/latest/summary.json`; treat `success: true` as pass.

Environment Flags

- `TEST_DETACHED=1` — run tests in detached mode; use `uv run test wait --json` to gate asynchronously.
- `JS_COUNT_STRATEGY=runtime` — report executed Hoot test counts instead of definition counts.
