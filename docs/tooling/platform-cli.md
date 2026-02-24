---
title: Platform CLI
---

Purpose

- Provide the platform-first operator contract for context selection,
  local runtime control, inspection metadata, and Dokploy deploy actions.

When

- Use for daily CM/OPW runtime workflows and Dokploy shipping checks.

Sources of Truth

- `tools/platform_cli.py` — command definitions and behavior.
- `platform/stack.toml` — context/instance contract.
- `platform/dokploy.toml` — Dokploy target branch/domain source of truth.
- `platform/secrets.toml` (optional, local) — layered secret/env overrides.

Quick start

- Validate platform config and list known contexts:

  ```bash
  uv run platform validate-config
  uv run platform list-contexts
  ```

- Select a runtime and inspect configuration:

  ```bash
  uv run platform select --context cm --instance local
  uv run platform select --context cm --instance local --dry-run
  uv run platform info --context cm --instance local
  uv run platform info --context cm --instance local --json-output
  uv run platform status --context cm --instance local
  uv run platform status --context cm --instance local --json-output
  ```

- Local runtime lifecycle:

  ```bash
  uv run platform up --context cm --instance local
  uv run platform up --context cm --instance local --build --no-cache
  uv run platform build --context cm --instance local --no-cache
  uv run platform logs --context cm --instance local --service web
  uv run platform down --context cm --instance local
  ```

- Orchestrated workflows and TUI launcher:

  ```bash
  uv run platform run --context cm --instance local --workflow restore --dry-run
  uv run platform run --context cm --instance dev --workflow restore \
    --env-file docker/config/cm-dev.env --dry-run
  uv run platform run --context cm --instance local --workflow restore-init-update
  uv run platform openupgrade --context cm --instance local --dry-run
  uv run platform tui
  uv run platform tui --context cm --instance local --workflow status
  ```

- Dokploy ship + rollback:

  ```bash
  uv run platform ship --context cm --instance testing
  uv run platform ship --context cm --instance testing --skip-gate
  uv run platform ship --context cm --instance testing --no-cache
  uv run platform ship --context cm --instance testing --timeout 1800
  uv run platform ship --context cm --instance testing --health-timeout 300
  uv run platform ship --context cm --instance testing --no-verify-health
  uv run platform ship --context cm --instance testing --dry-run
  uv run platform rollback --context cm --instance testing --list
  ```

- Dokploy env and deployment metadata helpers:

  ```bash
  uv run platform dokploy env-get \
    --context cm --instance testing --json-output
  uv run platform dokploy env-get \
    --context cm --instance testing --key ODOO_DB_NAME --show-values
  uv run platform dokploy env-set \
    --context cm --instance testing --set MY_KEY=my-value --dry-run
  uv run platform dokploy env-unset \
    --context cm --instance testing --prefix MY_ --dry-run
  uv run platform dokploy logs \
    --context cm --instance testing --limit 10 --json-output
  uv run platform dokploy reconcile --json-output
  uv run platform dokploy reconcile --context cm --instance prod --apply
  ```

- Environment/secrets layering introspection:

  ```bash
  uv run platform secrets explain --context cm --instance dev
  uv run platform secrets explain --context cm --instance dev --json-output
  uv run platform secrets explain --context cm --instance dev --show-values
  uv run platform secrets explain --context cm --instance dev --collision-mode error
  ```

Behavior notes

- `platform info` reports static runtime contract data plus Dokploy target
  resolution details when the target is `cm|opw` with `dev|testing|prod`.
- `platform status` reports local compose runtime state and latest Dokploy
  deployment details for deployable targets.
- `platform doctor` now includes both local runtime diagnostics and Dokploy
  target diagnostics in one payload.
- `platform build --no-cache` and `platform up --build --no-cache` force local
  Docker compose rebuilds without cache.
- `platform ship --no-cache` requests a Dokploy redeploy endpoint
  (`*.redeploy`), which is Dokploy's rebuild path.
- `platform ship` now verifies each target domain's health endpoint after a
  successful deployment when `--wait` is enabled.
- Health verification defaults to `https://<domain>/web/health` based on
  `platform/dokploy.toml` target domains (or
  `ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL` when domains are unavailable).
- Disable endpoint verification with `--no-verify-health` for one-off
  troubleshooting runs.
- `platform ship` reads gate policy from `platform/dokploy.toml`.
  `require_test_gate=true` runs `uv run test run --json --stack <context>`
  before deploy and `require_prod_gate=true` runs
  `uv run prod-gate backup --target <context>` before deploy.
- `platform/dokploy.toml` targets can optionally set
  `deploy_timeout_seconds`, `healthcheck_enabled`, `healthcheck_path`, and
  `healthcheck_timeout_seconds` to tune ship waits and endpoint checks per
  environment.
- Use `platform ship --skip-gate` to bypass those gates explicitly.
- `platform dokploy logs` returns deployment metadata (status, timestamps,
  log path).
- `platform dokploy reconcile` compares Dokploy targets against
  `platform/dokploy.toml` and can apply branch/auto-deploy/env fixes via
  `--apply`.
- Direct log streaming remains gated behind Dokploy websocket session auth.
- `platform run` provides safe orchestration for restore/init/update/
  openupgrade and restore-chain workflows.
- Platform env merge order for context-aware commands is:
  `.env`/`--env-file` -> `secrets.toml` shared -> context shared ->
  instance env overrides.
- Runtime tuning keys can be declared in `platform/stack.toml` under
  `runtime_env` at stack/context/instance scope. Merge order is
  `stack -> context -> instance`.
- On conflicting key values across layers, platform emits a collision warning by
  default. Set `PLATFORM_ENV_COLLISION_MODE=error` to fail-closed or
  `PLATFORM_ENV_COLLISION_MODE=ignore` to suppress warnings.
- `platform select --dry-run` shows context/instance env diff before writing
  `.platform/env/<context>.<instance>.env`.
- Platform runtime control files (for example generated
  `platform.odoo.conf`) are written under `.platform/state/` by default.
- `platform run --workflow restore` now generates/uses
  `.platform/env/<context>.<instance>.env` by default (same layering contract
  as `platform select`), so restore no longer implicitly prefers legacy
  `docker/config/*.env` files.
- Pass `--env-file ...` only for explicit one-off restore overrides.
- Restore now performs a filestore capacity preflight before starting upstream
  copy. If local free space is insufficient, it fails fast with a clear error
  (instead of failing mid-transfer after DB work).
- When `ODOO_FILESTORE_OWNER` is unset, restore now auto-aligns filestore
  ownership to the mounted data volume owner so web workers can write/read
  generated asset attachments after restore.
- Restore now always targets the DB-specific local filestore directory
  (`<ODOO_FILESTORE_PATH>/<ODOO_DB_NAME>` when needed), so restored blobs and
  database attachment pointers stay aligned.
- Restore now reconciles post-OpenUpgrade module state by demoting
  missing-manifest `to install` modules back to `uninstalled` when they were
  already uninstalled before OpenUpgrade, then applies a fail-closed check so
  any remaining unresolved install queue entries abort restore with a clear
  error.
- Web bootstrap now starts its runtime config from
  `/volumes/config/_generated.conf` when present, preserving generated Odoo
  tuning values (for example workers, db_maxconn, and time/memory limits).
- Dokploy targets pin `ODOO_WEB_COMMAND` to
  `python3 /volumes/scripts/run_odoo_bootstrap.py -c /tmp/platform.odoo.conf`
  so remote compose deploys use the same bootstrap/runtime contract as local.
- For OPW-sized filestores, local Docker Desktop volume limits may be too low;
  treat full OPW restore as remote-first unless local Docker storage is
  expanded.
- `platform tui` prompts for context, instance, and workflow so a single
  runconfig can launch the operator flow.

Key notes

- `ODOO_KEY` is used during restore provisioning to seed deterministic GPT
  service users/API keys (`docs/tooling/gpt-service-user.md`). Treat it as a
  high-privilege secret.
