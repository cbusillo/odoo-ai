---
title: Platform Command Patterns
---

Purpose

- Provide the common `uv run platform ...` command patterns without mixing
  them into the stable operator contract.

When

- When you know you need the platform CLI and want concrete invocation
  examples.

Sources of Truth

- [@docs/tooling/platform-cli.md](platform-cli.md) — canonical operator
  contract and command boundaries.
- `tools/platform/cli.py` — Click entrypoint and option surface.
- `platform/stack.toml` — context and instance contract.
- `platform/dokploy.toml` — remote deployment contract.

Quick Start

- Validate platform config and list contexts:

  ```bash
  uv run platform validate-config
  uv run platform list-contexts
  ```

- Select and inspect a local runtime:

  ```bash
  uv run platform select --context cm --instance local
  uv run platform info --context cm --instance local
  uv run platform status --context cm --instance local
  ```

- Local runtime lifecycle:

  ```bash
  uv run platform up --context cm --instance local
  uv run platform build --context cm --instance local --no-cache
  uv run platform odoo-shell --context cm --instance local \
    --script tmp/scripts/example.py
  uv run platform logs --context cm --instance local --service web
  uv run platform down --context cm --instance local
  ```

- Promote reusable local validation scenarios out of `tmp/scripts/` into
  tracked scripts under `tools/validate/`, then invoke them through
  `platform odoo-shell` until a dedicated `platform validate ...` command
  exists:

  ```bash
  uv run platform odoo-shell --context opw --instance local \
    --script tools/validate/shopify_roundtrip.py
  ```

- Remote validation scenarios can be promoted into tracked `uv run` scripts
  when they rely on XML-RPC/HTTP rather than local Odoo shell execution. For
  example:

  ```bash
  uv run python tools/validate/shopify_roundtrip.py --context opw --instance testing
  ```

Local Workflow Patterns

- Run destructive data workflows:

  ```bash
  uv run platform restore --context cm --instance local --dry-run
  uv run platform bootstrap --context cm --instance local --dry-run
  uv run platform restore --context cm --instance testing --dry-run
  uv run platform openupgrade --context cm --instance local --dry-run
  ```

- `platform restore` and `platform bootstrap` block prod data-mutation
  workflows by default.
  Use `--allow-prod-data-workflow` only for explicit break-glass operations.
- `platform restore` and `platform bootstrap` now generate and use
  `.platform/env/<context>.<instance>.env` by default. Pass `--env-file ...`
  only for explicit one-off overrides.
- `platform restore` and `platform bootstrap` now require the remote target to
  be pinned in `platform/dokploy.toml`; the workflow reads the target id from
  source of truth instead of rediscovering it through env overrides.
- Dokploy-managed restore/bootstrap now execute through Dokploy schedule jobs,
  not host SSH. The only remaining SSH hop in the restore path is the upstream
  source host accessed by `run_odoo_data_workflows.py`.
- Restore performs a filestore capacity preflight before upstream copy.
- Restore acquires a shared lock file (`ODOO_DATA_WORKFLOW_LOCK_FILE`, default
  `/volumes/data/.data_workflow_in_progress`) so bootstrap waits for restore
  completion.
- Restore targets the DB-specific filestore directory and reconciles
  post-OpenUpgrade module state fail-closed.

Remote Release Patterns

- Ship and rollback:

  ```bash
  uv run platform ship --context cm --instance testing
  uv run platform ship --context cm --instance testing --skip-gate
  uv run platform ship --context cm --instance testing --source-ref release/cm-hotfix
  uv run platform ship --context cm --instance testing --source-ref HEAD
  uv run platform ship --context cm --instance testing --dry-run
  uv run platform rollback --context cm --instance testing --list
  ```

- `platform ship` fails closed when tracked files are dirty.
  Prefer a clean worktree and `--source-ref HEAD`; use `--allow-dirty` only as
  an explicit exception.
- `platform ship` syncs the deployment branch before deploy/redeploy.
  Default source refs come from `platform/dokploy.toml`.
- Managed Dokploy targets use `platform ship` as the only deployment trigger.
  Leave Dokploy auto deploy disabled so branch sync does not race the
  explicit deploy call.
- `platform ship` verifies `/web/health` by default when `--wait` is enabled.
  `--no-verify-health` is for one-off troubleshooting.
- Release-sensitive commands (`ship`, `rollback`, `gate`, `promote`, and
  `platform dokploy reconcile`) always resolve env layers with collision mode
  `error`.
- `platform rollback` currently works only for Dokploy application targets.
  Compose targets must use Dokploy UI rollback controls.

Release Gates and Promotion

```bash
uv run platform gate --context cm --instance testing --phase all
uv run platform promote --context cm --from-instance testing --to-instance prod
```

- `platform gate --phase code` runs the local test gate.
- `platform gate --phase env` verifies live endpoint health.
- `platform promote` is intentionally limited to `testing -> prod` and runs
  `uv run prod-gate backup --target <context>` before deployment.

Dokploy Helpers

```bash
uv run platform dokploy env-get --context cm --instance testing --json-output
uv run platform dokploy env-set --context cm --instance testing \
  --set MY_KEY=my-value --dry-run
uv run platform dokploy logs --context cm --instance testing --limit 10 --json-output
uv run platform dokploy reconcile --json-output
uv run platform dokploy reconcile --context cm --instance prod --apply
```

- `platform dokploy reconcile` is fail-closed and validates every target
  against `platform/stack.toml`.
- `platform dokploy reconcile --prune-env --apply` removes reconcile-managed
  remote env keys absent from `platform/dokploy.toml`.
- Managed Dokploy helper commands now require `target_id` in
  `platform/dokploy.toml`; name-based target discovery is no longer part of
  the steady-state contract.
- Direct log streaming remains gated behind Dokploy websocket session auth.

TUI Patterns

```bash
uv run platform tui --context cm --instance local --workflow status
uv run platform tui --context all --instance local --workflow status
uv run platform tui --context cm --instance testing --workflow ship
```

- `platform tui` prompts for context, instance, and workflow when not fully
  specified.
- In a TTY with `questionary` available, it uses interactive list selection and
  falls back to typed prompts otherwise.
- Wildcard or comma-separated fan-out runs are restricted to read-only
  `status` and `info` workflows.
- `platform tui --workflow ship` requires an explicit single target.
- Add `--json` or `--json-output` to emit a single aggregated fan-out summary.

Secrets and Runtime Artifacts

- Use `platform secrets explain` to inspect the env layering contract:

  ```bash
  uv run platform secrets explain --context cm --instance dev
  uv run platform secrets explain --context cm --instance dev --json-output
  ```

- Env merge order is `.env` or `--env-file` -> `secrets.toml` shared ->
  context shared -> instance env.
- Runtime tuning keys live under `runtime_env` in `platform/stack.toml` with
  merge order `stack -> context -> instance`.
- `platform select --dry-run` shows the env diff before writing
  `.platform/env/<context>.<instance>.env`.
- `platform select` also writes `.platform/ide/<context>.<instance>.odoo.conf`
  for JetBrains tooling.
- Platform runtime control files (for example generated `platform.odoo.conf`)
  are written under `.platform/state/`.
- Dokploy targets pin `ODOO_WEB_COMMAND` to
  `python3 /volumes/scripts/run_odoo_startup.py -c /tmp/platform.odoo.conf`
  so remote compose deploys use the same startup/runtime contract as local.

Operational Notes

- `platform doctor` spans both worlds: local diagnostics for `--instance local`
  and Dokploy target diagnostics for remote instances.
- Platform no longer mirrors Odoo core or enterprise sources into the repo;
  PyCharm remote interpreters should use IDE-managed remote sources.
- `ODOO_KEY` seeds deterministic GPT service users and API keys during restore.
  See [@docs/tooling/gpt-service-user.md](gpt-service-user.md).
- For OPW-sized filestores, local Docker Desktop volume limits may be too low;
  treat full OPW restore as remote-first unless local Docker storage is
  expanded.
