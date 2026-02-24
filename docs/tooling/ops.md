---
title: Ops CLI
---

Purpose

- Document the legacy Ops CLI during platform migration.

Status

- `uv run platform ...` is the primary operator path.
- `uv run ops ...` is transitional compatibility only and should not be used for
  new workflow automation.
- Prefer `@docs/tooling/platform-cli.md` for current commands.

When

- Local stack operations, shipping, or production gates.

Sources of Truth

- `tools/ops_cli.py` — command definitions and behavior.
- `docker/config/ops.toml` — targets and Coolify host mapping.

Quick start

- Run the interactive menu:

  ```bash
  uv run ops
  ```

- Example shortcuts:

  ```bash
  uv run ops local init opw
  uv run ops local restore opw
  uv run ops local up all
  uv run ops local down all
  uv run ops local restart opw
  uv run ops local upgrade opw
  uv run ops local upgrade-restart opw
  uv run ops local openupgrade opw
  uv run ops local doctor opw
  uv run ops local info opw --json
  uv run ops local shell opw
  uv run ops local shell opw <<'PY'
  env['res.users'].search([]).mapped('name')
  PY
  uv run ops local exec opw -- /odoo/odoo-bin shell -d opw -c /volumes/config/_generated.conf
  uv run ops local up opw --build --no-cache

  uv run ops ship testing opw
  uv run ops ship testing all
  uv run ops ship testing all --serial
  uv run ops ship testing cm --no-cache
  uv run ops ship prod opw --confirm
  uv run ops ship prod cm --no-cache --confirm
  uv run ops ship testing opw --after restore

  uv run ops gate opw --confirm

  uv run ops status testing opw
  uv run ops status testing all --no-wait
  uv run ops coolify app-logs --apps opw-testing --lines 200
  ```

Remembered choices

- The menu remembers your last selections in:
  `~/odoo-ai/ops.json`.
- Favorites are derived from recent usage and shown as quick picks (up to 6).
- After an interactive run, the CLI prints the equivalent `uv run ops ...`
  command for copy/paste.
- Interactive prompts use arrow keys when `questionary` is available; otherwise
  they fall back to typed prompts.
- Install `rich` + `questionary` with `uv sync`.

Configuration

- Source of truth: `docker/config/ops.toml` (targets + Coolify host). Branches,
  app names, and local stack/env paths follow conventions by default. No secrets
  live in this file.
- Prod bootstrap guard: defaults to disabled. Set `allow_prod_init = true` under
  a target in `docker/config/ops.toml` (or export `OPS_ALLOW_PROD_INIT=1`) to
  allow `uv run ops ship prod <target> --after init`.
- Prod restore guard: defaults to disabled. Set `allow_prod_restore = true`
  under a target in `docker/config/ops.toml` (or export
  `OPS_ALLOW_PROD_RESTORE=1`) to allow `uv run ops ship prod <target> --after restore`.

Conventions

- Local stack name: `{target}-local`.
- Local env file: `docker/config/{target}-local.env` (or `local_env_file` from
  `docker/config/ops.toml`).
- Branch names: `{target}-dev`, `{target}-testing`, `{target}-prod`.
- Coolify app names: `{target}-dev`, `{target}-testing`.

Targets & environments

- Targets: the keys under `[targets]` in `docker/config/ops.toml`, plus `all`.
  `all` expands to targets with `include_in_all = true` (default).
- Environments: `local`, `dev`, `testing`, `prod`.

Behavior notes

- Local actions run deployer helpers directly and use the stack env files
  (`docker/config/{target}-local.env`).
- Local actions enforce security guardrails: `ODOO_MASTER_PASSWORD` must be set
  and `ODOO_LIST_DB` must be `False` to keep the database manager disabled.
- `uv run ops local info` prints machine-readable stack metadata (paths + identifiers
  only; no secrets) derived from `load_stack_settings()`.
- Restore/init runs `docker/scripts/restore_from_upstream.py` (restore/boot,
  sanitize, addon updates, and environment cleanups). If installed, the
  `environment_overrides` addon applies `ENV_OVERRIDE_*` settings for SSO and
  integrations after each restore.
- Restore now reconciles missing-manifest `to install` modules back to
  `uninstalled` when they were already uninstalled before OpenUpgrade, then
  fails closed if unresolved install-queue entries still remain. This prevents
  partially upgraded module graphs from booting.
- `uv run ops local restart` performs a fast `docker compose restart web` for the
  target stack.
- `uv run ops local down` removes orphaned containers and anonymous volumes for
  the target stack while preserving named volumes.
- `uv run ops local upgrade` runs module upgrades using the stack's configured
  module list (AUTO by default) without rebuilding the image. If
  `ODOO_INSTALL_MODULES` is set, it installs any missing modules from that list
  before upgrading. This applies to local and remote deploy upgrades.
- `uv run ops local upgrade-restart` runs the upgrade then restarts the web service.
- `uv run ops local openupgrade` runs the OpenUpgrade pipeline against the current
  database without restoring from upstream and resets module versions for
  modules that have OpenUpgrade scripts so their scripts re-run.
- `uv run ops local exec <target> -- <command>` runs a command in the script-runner
  container using the merged stack env. Env values are forwarded by name (no
  values in argv), so secrets are not echoed in process args or dry-run output.
  Use `--service` to target a different service or `--no-env` to skip passing
  the merged env into the exec.
- `uv run ops local shell <target>` runs the Odoo shell inside the script-runner
  using the merged stack env and defaults (`-d $ODOO_DB_NAME -c
  /volumes/config/_generated.conf`). Pass extra args after `--` to override
  defaults (for example, `-- --log-level=debug`).
- `uv run ops ship prod <target> --after init` runs a prod bootstrap-only init
  via Coolify (sets the post-deploy command, deploys, waits for completion,
  then restores the previous post-deploy command). Requires the prod init guard.
- `--no-cache` forces a clean local build; for `all`, only the first local
  target uses `--no-cache` and the rest use normal cache.
- `uv run ops ship <env> <target> --no-cache` requests a force rebuild from
  Coolify (`start?force=true`) for that deployment.
- Ship actions push to the correct branch:
  - `opw-testing`, `cm-testing`, `opw-dev`, `cm-dev`, `opw-prod`, `cm-prod`.
- Ship actions for dev/testing can optionally run a post-deploy `restore`,
  `init`, or `upgrade` via Coolify post-deployment commands (requires
  `--wait`). Prod allows `--after init` only when the prod init guard is
  enabled, and `--after restore` only when the prod restore guard is enabled
  (both require confirmation).
- When `--after restore`/`--after init`/`--after upgrade` is set, ops waits for
  the post-deploy command and web login to finish (default `--wait`).
  `--no-wait` cannot be used with `--after`.
- Prod ships default to `--after upgrade` to update addons on deploy.
- Prod ship runs the prod gate first using `uv run prod-gate backup`.
- Prod actions require an explicit confirmation (interactive prompt or
  `--confirm` for non-interactive usage).
- For testing, `uv run ops ship` runs the test gate before deploy (skip with
  `--skip-tests`).
- For dev/testing, `uv run ops ship` triggers a Coolify deploy by default (use
  `--no-deploy` to skip). Deploy waits are on by default; use `--no-wait` to
  skip (not compatible with `--after`).
- `uv run ops coolify env-set` can push env vars to one or more Coolify apps
  (reads env files via the same parser as other ops tooling).
- `uv run ops coolify env-get` can fetch env vars from one or more Coolify apps
  with optional prefix/key filters for quick audits (values are redacted unless
  `--show-values` is supplied).
- `uv run ops coolify env-unset` can remove env vars from one or more Coolify apps
  using key/prefix filters.
- `uv run ops coolify logs` can fetch the latest deployment logs from Coolify.
  Defaults to override/post-deploy markers; use `--all` or `--pattern` for
  broader output.
- `uv run ops coolify app-logs` can fetch runtime application logs via the
  Coolify API. For compose apps, it prefers SSH + Docker logs from the app's
  runtime server (favoring the `web` service container) and falls back to the
  Coolify API endpoint when SSH is unavailable.
- Use `--serial` to deploy one target at a time when shipping `all`.
- `uv run ops status` uses the Coolify API and requires `COOLIFY_TOKEN` (waits by
  default; use `--no-wait`).
- For interactive runs, `uv run ops --no-wait` skips deploy waiting.
- Local actions default to `--no-build` for speed; pass `--build` to force a rebuild.
- `ODOO_INSTALL_MODULES` controls the install list on init/restore. Use this to
  guarantee key addons are installed.
  For non-prod, include `environment_overrides` here; omit it for prod once
  the instance is promoted.
- `ODOO_UPDATE_MODULES=AUTO` upgrades all installed local addons; explicit lists
  only update the modules named.
