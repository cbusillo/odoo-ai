Title: Test CLI (uv)

Commands

- `uv run test run` — all phases with parallel sharding; add `--json` for gate-mode output.
- `uv run test unit|js|integration|tour` — phase-scoped loops; combine with module filters to minimize scope.
- `uv run test wait --json` — poll detached runs and return a single JSON payload.
- `uv run test plan --phase all` — inspect sharding/phase allocations before a large run.

Scoping Flags

- Global: `--modules a,b`, `--exclude x,y` (works with `test run`, `test plan`).
- Per phase: `--unit-modules`, `--js-modules`, `--integration-modules`, `--tour-modules` (and matching `--*-exclude`).
- Sharding: `--unit-shards`, `--js-shards`, `--integration-shards`, `--tour-shards`.

Summaries

- Parse `tmp/test-logs/latest/summary.json`; treat `success: true` as the definitive result.
- Phase-specific summaries live under `tmp/test-logs/latest/<phase>/summary.json` when you need finer detail.

Environment Flags

- `TEST_DETACHED=1` — fire a detached run; follow up with `uv run test wait --json`.
- `JS_COUNT_STRATEGY=runtime` — report executed Hoot test counts instead of definition counts.
