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

- Select and inspect a local runtime through `odoo-devkit` and a tenant
  manifest:

    ```bash
    uv --directory ../odoo-devkit run platform runtime select \
      --manifest ../odoo-tenant-cm/workspace.toml
    uv --directory ../odoo-devkit run platform runtime inspect \
      --manifest ../odoo-tenant-cm/workspace.toml
    uv run platform info --context cm --instance local
    uv run platform status --context cm --instance local
    ```

- Local runtime lifecycle ownership now lives in `odoo-devkit`:

    ```bash
    uv --directory ../odoo-devkit run platform runtime build \
      --manifest ../odoo-tenant-cm/workspace.toml --no-cache
    uv --directory ../odoo-devkit run platform runtime up \
      --manifest ../odoo-tenant-cm/workspace.toml --build
    uv --directory ../odoo-devkit run platform runtime down \
      --manifest ../odoo-tenant-cm/workspace.toml --volumes
    ```

- The repo-local `platform select|up|down|logs|build|inspect|odoo-shell`
  commands in `odoo-ai` are retired compatibility shims that now hand off to
  the manifest-backed `odoo-devkit` runtime surface.

- Local debugging helpers now live there too:

    ```bash
    uv --directory ../odoo-devkit run platform runtime logs \
      --manifest ../odoo-tenant-cm/workspace.toml --service web --no-follow
    uv --directory ../odoo-devkit run platform runtime psql \
      --manifest ../odoo-tenant-cm/workspace.toml -- -c 'select 1'
    uv --directory ../odoo-devkit run platform runtime odoo-shell \
      --manifest ../odoo-tenant-cm/workspace.toml --script tmp/scripts/example.py
    ```

- Run tracked environment validation scenarios through `platform validate`:

    ```bash
    uv run platform validate shopify-roundtrip --context opw --instance testing \
      --profile smoke --sample-size 5
    ```

- Prefer explicit profiles for long-running scenarios. For Shopify validation,
  `--profile smoke` resets Shopify and re-exports a bounded sample before the
  round-trip checks, `--profile standard` keeps the bounded sample but runs
  multiple deep round-trip products, and `--profile full` prepares with a full
  export.
- `shopify-roundtrip` is disabled on `prod`; use it only on non-production
  instances where destructive round-trip validation is appropriate.

Local Workflow Patterns

- Run destructive data workflows:

    ```bash
    uv --directory ../odoo-devkit run platform runtime restore \
      --manifest ../odoo-tenant-cm/workspace.toml
    uv --directory ../odoo-devkit run platform runtime workflow \
      --manifest ../odoo-tenant-cm/workspace.toml --workflow bootstrap
    uv run platform restore --context cm --instance testing --dry-run
    uv --directory ../odoo-devkit run platform runtime workflow \
      --manifest ../odoo-tenant-cm/workspace.toml --workflow openupgrade
    ```

- In `odoo-ai`, `platform restore` and `platform bootstrap` now survive only
  for Dokploy-managed remote targets. Local restore/bootstrap hand off to the
  manifest-backed `odoo-devkit` runtime surface.

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
    uv run platform ship --context cm --instance testing --dry-run
    uv run platform rollback --context cm --instance testing --list
    ```

- `platform ship` fails closed when tracked files are dirty.
  Prefer a clean worktree; use `--allow-dirty` only as an explicit exception.
- Managed Dokploy targets use `platform ship` as the only deployment trigger.
  Leave Dokploy auto deploy disabled so the explicit deploy call remains the
  only release trigger.
- `platform ship` verifies `/web/health` by default when `--wait` is enabled.
  `--no-verify-health` is for one-off troubleshooting.
- Release-sensitive commands (`ship`, `rollback`, `gate`, and
  `platform dokploy reconcile`) always resolve env layers with collision mode
  `error`.
- `platform rollback` currently works only for Dokploy application targets.
  Compose targets must use Dokploy UI rollback controls.

Release Gates and Handoff

```bash
uv run platform gate --context cm --instance testing --phase all
uv run --project ../odoo-control-plane control-plane promote resolve \
  --context cm --from-instance testing --to-instance prod \
  --artifact-id <artifact-id> --backup-record-id <record-id>
```

- `platform gate --phase code` runs the local test gate.
- `platform gate --phase env` verifies live endpoint health.
- Native `odoo-control-plane` ship and promotion planning/execution no longer
  require an `odoo-ai` request export or path-based runtime delegation.

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
- For extracted tenants, `platform runtime select --manifest ...` in
  `odoo-devkit` writes the runtime env and JetBrains-visible Odoo config for
  the manifest-backed workspace.
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
