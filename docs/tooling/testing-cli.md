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
  shards, timeouts, failures). Requires `llm.json` (created by the runner) and
  now includes phase outcome kinds, top failure reasons, and host resource
  budgets.
- `uv run test plan --phase all` — inspect sharding/phase allocations before a
  large run.
- `uv run test run` writes `tmp/test-logs/<session>/run-plan.json` before shard
  execution starts so phase groups, worker limits, and shard allocations are
  explicit before side effects begin.
- `run-plan.json` also records host-level resource budgets under
  `host_resources` so browser-heavy and production-clone-heavy concurrency is
  explicit before execution begins.
- `uv run test validate --json` — verify all tests executed + summarize
  failures. Validation output now also includes phase outcome kinds and the
  host resource budget recorded in the run plan.
- `--stack opw|cm` (or `--env-file .platform/env/<context>.<instance>.env`) —
  load the matching local stack env before running.
- Test runs require a resolved stack context. Stack-based runs fail closed when
  `.platform/env/<context>.<instance>.env` is missing; generate it first with
  `uv run platform select --context <context> --instance <instance>`.

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
- `TESTKIT_PROFILE=gate` applies deterministic gate defaults for local code
  gate runs with the reproducible shard/process/memory defaults from
  `tools/testkit/cli.py`. Use it for gate behavior, not interactive loops.
- `TESTKIT_BROWSER_SLOTS=1` — host-level cap for concurrent JS/tour shard
  execution.
- `TESTKIT_PRODUCTION_CLONE_SLOTS=2` — host-level cap for concurrent
  production-clone shard execution.
- `TOUR_STEP_DELAY_SECONDS=0` is the fixture default for tour tests. Set a
  non-zero value only for local debugging when you need slower visual stepping.
- Named-volume controls for DB/data/logs live under the `TESTKIT_*_VOLUME_*`
  env vars in `tools/testkit/docker_api.py`. Use them when macOS Docker volume
  behavior needs tuning or cleanup after runs.
- `TESTKIT_SHARD_TIMEOUT=1800` — hard cap for any single shard (seconds). If
  set, it overrides the per-phase timeout from `pyproject.toml`.
- Template reuse defaults can be set in `pyproject.toml` under
  `[tool.odoo-test.template]` (`reuse`, `ttl_sec`). Env vars
  `REUSE_TEMPLATE` and `TEMPLATE_TTL_SEC` override the defaults.
- Unit/JS templates and production-clone templates are prepared eagerly per
  phase before shard fanout so resource failures happen earlier and are easier
  to classify.
- Browser-heavy and production-clone-heavy shard execution now respects shared
  host budgets across concurrent phases so overlap mode cannot overrun the
  machine just because separate phases each looked safe in isolation.

Artifacts

- `tmp/test-logs/<session>/llm.json` — LLM-friendly rollup (flat failures with
  `module`/`class`/`test_name` when available, grouped failures, per-phase
  counters, phase `outcome_kinds`, shard summaries with `outcome_kind` /
  `failure_reasons`, timeouts/container names, repro commands, and key artifact
  paths).
- Per-shard `*.summary.json` files now classify failures explicitly with
  `outcome_kind` (`success`, `test_failure`, `infra_failure`,
  `harness_failure`) plus `failure_reasons` so harness/runtime issues stop
  blending into addon test failures.
