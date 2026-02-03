---
title: Test CLI (uv)
---


Purpose

- Provide the canonical test runner commands and flags.

When

- Anytime tests are run or gated.

Sources of Truth

- `pyproject.toml` ([project.scripts]) for entry points.
- `tools/testkit/` for sharding and execution behavior.

Commands

- `uv run test run` — all phases with parallel sharding; add `--json` for
  gate-mode output.
- `uv run test unit|js|integration|tour` — phase-scoped loops; combine with
  module filters to minimize scope.
- `uv run test wait --json` — poll detached runs and return a single JSON
  payload.
- `uv run test doctor-session --json` — summarize the latest session (slowest
  shards, timeouts, failures). Requires `llm.json` (created by the runner).
- `uv run test plan --phase all` — inspect sharding/phase allocations before a
  large run.
- `uv run test validate --json` — verify all tests executed + summarize
  failures.
- `--stack opw|cm` (or `--env-file docker/config/<stack>-local.env`) —
  load the matching local stack env before running. When a `*-ci-local` stack
  exists (for example `cm-ci-local`), `--stack cm` automatically prefers the
  CI stack. Use `--stack cm-local` to target the dev stack explicitly.
- Test runs require a resolved stack context; the harness refuses to run
  without one to avoid starting an unintended default stack.

Scoping Flags

- Global: `--modules a,b`, `--exclude x,y` (works with `test run`, `test plan`).
- Per phase: `--unit-modules`, `--js-modules`, `--integration-modules`,
  `--tour-modules` (and matching `--*-exclude`).
- Sharding: `--unit-shards`, `--js-shards`, `--integration-shards`,
  `--tour-shards`.

Summaries

- Parse `tmp/test-logs/latest/summary.json`; treat `success: true` as the
  definitive result.
- Phase-specific summaries live under
  `tmp/test-logs/latest/<phase>/summary.json` when you need finer detail.

Environment Flags

- Detached runs are managed via the `--detached` CLI flag; use
  `uv run test wait --json` to follow progress.
- `COVERAGE_PY=1` — enable targeted Python coverage collection for test runs.
- `COVERAGE_MODULES=addon_a,addon_b` — limit coverage to specific addons; reports
  land in `tmp/test-logs/<session>/coverage/`.
- `ODOO_DEV_MODE` is cleared during test runs to avoid autoreload interruptions.
- `TESTKIT_DISABLE_DEV_MODE=1` (default for `uv run test --stack`) forces
  `--dev=none`, including tours; set to `0` if you need `--dev=assets` while
  debugging JS/tours.
- `TESTKIT_DB_VOLUME_MODE=named` — use a named Docker volume for the test DB
  (recommended on macOS CI stacks to avoid gRPC-FUSE crashes).
- `TESTKIT_DB_VOLUME_NAME=testkit_db` — override the named volume key.
- `TESTKIT_DB_VOLUME_CLEANUP=1` — remove the named test DB volume after the run.
- `TESTKIT_DATA_VOLUME_MODE=named` — use a named Docker volume for `/volumes/data`.
- `TESTKIT_DATA_VOLUME_NAME=testkit_data` — override the named data volume key.
- `TESTKIT_DATA_VOLUME_CLEANUP=1` — remove the named data volume after the run.
- `TESTKIT_LOG_VOLUME_MODE=named` — use a named Docker volume for `/volumes/logs`.
- `TESTKIT_LOG_VOLUME_NAME=testkit_logs` — override the named log volume key.
- `TESTKIT_LOG_VOLUME_CLEANUP=1` — remove the named log volume after the run.
- `TESTKIT_VOLUME_CLEANUP=1` — remove all named testkit volumes after the run.
- `TESTKIT_SHARD_TIMEOUT=1800` — hard cap for any single shard (seconds). If
  set, it overrides the per-phase timeout from `pyproject.toml`.
- Template reuse defaults can be set in `pyproject.toml` under
  `[tool.odoo-test.template]` (`reuse`, `ttl_sec`). Env vars
  `REUSE_TEMPLATE` and `TEMPLATE_TTL_SEC` override the defaults.

Artifacts

- `tmp/test-logs/<session>/llm.json` — LLM-friendly rollup (flat failures with
  `module`/`class`/`test_name` when available, grouped failures, per-phase
  counters, shard summaries with timeouts/container names, repro commands, and
  key artifact paths).
