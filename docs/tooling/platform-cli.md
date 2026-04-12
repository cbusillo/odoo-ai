---
title: Platform CLI
---

Purpose

- Define the canonical operator contract for `uv run platform ...` and the
  boundary between local runtime workflows and Dokploy-managed remote targets.

When

- Use before changing platform workflows, docs, or run configurations.

Sources of Truth

- `tools/platform/cli.py` — Click entrypoint and command implementation.
- `tools/platform/models.py` — typed platform data contracts.
- `tools/platform/environment.py` — env layering and stack/source loading.
- `tools/platform/runtime.py` — runtime selection and env file rendering.
- `tools/platform/dokploy.py` — Dokploy API and deploy-health orchestration.
- `tools/platform/release_workflows.py` — release gate logic.
- `platform/stack.toml` — context and instance contract.
- `platform/dokploy.toml` — remote target branch/domain contract.
- `platform/secrets.toml` (optional, local) — layered secret/env overrides.

Operator Contract

- `local` is the only host runtime on this machine.
- The repo-local local-runtime lifecycle commands `platform select`, `up`,
  `down`, `logs`, `build`, `inspect`, and `odoo-shell` are retired in
  `odoo-ai` and now fail closed.
- The direct repo-local workflow commands `platform init`, `platform update`,
  and `platform openupgrade` are also retired in `odoo-ai` and now hand off to
  the manifest-backed `odoo-devkit` runtime workflow surface.
- For extracted tenant local runtime work, use `odoo-devkit` with the tenant's
  tracked `workspace.toml`, for example:
  `uv --directory /path/to/odoo-devkit run platform runtime build --manifest /path/to/workspace.toml --no-cache`.
  Or build plus start the stack with:
  `uv --directory /path/to/odoo-devkit run platform runtime up --manifest /path/to/workspace.toml --build`.
  Stopping that local runtime now lives there too:
  `uv --directory /path/to/odoo-devkit run platform runtime down --manifest /path/to/workspace.toml --volumes`.
- Manifest-backed local debugging now lives there too, for example:
  `uv --directory /path/to/odoo-devkit run platform runtime logs --manifest /path/to/workspace.toml --service web --no-follow`
  and
  `uv --directory /path/to/odoo-devkit run platform runtime psql --manifest /path/to/workspace.toml -- -c 'select 1'`.
  Manifest-backed local shell access also lives there:
  `uv --directory /path/to/odoo-devkit run platform runtime odoo-shell --manifest /path/to/workspace.toml --script /path/to/script.py`.
- Local destructive runtime work also moved there:
  `uv --directory /path/to/odoo-devkit run platform runtime restore --manifest /path/to/workspace.toml`
  and
  `uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow bootstrap`.
- Treat `dev`, `testing`, and `prod` as Dokploy-managed remote targets.
  Use `platform ship`, `platform rollback`, and `platform gate` from `odoo-ai`.
  For destructive remote data workflows, use the same manifest-backed
  `odoo-devkit` commands with an explicit runtime `--instance`, for example
  `uv --directory /path/to/odoo-devkit run platform runtime restore --manifest /path/to/workspace.toml --instance testing`.
- `platform ship` is the non-destructive remote deploy/restart path.
- `platform rollback` currently supports Dokploy application targets only.
  Compose targets must use Dokploy UI rollback controls.
- `platform restore` is the destructive upstream-data replacement path.
- `platform bootstrap` is the destructive fresh-start rebuild path.
- `platform validate <scenario>` runs tracked environment validation scenarios
  against a selected stack or managed target.
- `platform validate importer-health --context cm --instance local` snapshots
  CM, Fishbowl, and RepairShopr importer run state, resume cleanliness, and
  external-ID coverage signals without relying on scratch scripts. The CM
  snapshot also reports placeholder-employee attendance warnings so zero-hour
  and open-placeholder punches stay visible after imports.
- `platform validate importer-health --importer cm-data --importer fishbowl`
  scopes the importer-health scenario to a subset of importers when you only
  need to re-check one workflow after a targeted import or restore.

Command Families

- Local inspection: `info`, `status`, `doctor`.
- Retired compatibility shims: `select`, `up`, `down`, `logs`, `build`,
  `inspect`, `odoo-shell`, `init`, `update`, `openupgrade`.
- Retired compatibility shims: `restore`, `bootstrap`, `run`.
- Validation scenarios: `validate ...`.
- Remote release: `ship`, `rollback`, `gate`, and `platform dokploy ...`
  helpers.
- Dokploy inventory: `platform dokploy inventory` for project/server/target
  snapshots before teardown, recreation, or reconciliation work.
- Secrets/env introspection: `platform secrets explain`.
- Interactive launcher: `platform tui`.

Behavior Highlights

- Manifest-driven `platform runtime ...` ownership now lives in `odoo-devkit`.
  This document remains the contract for the shrinking repo-local
  `uv run platform ...` surface in `odoo-ai` during retirement.
- `odoo-ai` is not the durable final home for this platform surface. The
  remaining repo-local commands and docs should be treated as migration seams
  to be extracted into tenant repos, `odoo-devkit`, or `odoo-control-plane`.
- `platform select`, `up`, `down`, `logs`, `build`, `inspect`, and
  `odoo-shell` now exist only as explicit retirement shims so operators get a
  precise migration message instead of silently using the wrong repo.
- `platform logs` now points at the manifest-backed `odoo-devkit` runtime logs
  helper, and `platform odoo-shell` now points at the manifest-backed
  `odoo-devkit` runtime shell helper. `platform down` now points at the
  manifest-backed `odoo-devkit` runtime down helper, and `platform build` now
  points at the manifest-backed `odoo-devkit` runtime build helper.
- `platform init`, `platform update`, and `platform openupgrade` now also
  exist only as explicit retirement shims. Use
  `uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow <name>`
  instead.
- `platform restore`, `platform bootstrap`, and `platform run` in `odoo-ai`
  are now retired too. Use the manifest-backed `odoo-devkit` runtime
  restore/bootstrap surface instead, and pass `--instance` explicitly when
  targeting Dokploy-managed `dev`/`testing`/`prod`.
- `platform doctor` is read-only and spans both local runtime diagnostics and
  Dokploy target diagnostics.
- `platform ship` fails closed on dirty tracked files. Prefer a clean worktree
  for surgical remote testing.
- `platform ship` is the only supported remote deployment trigger for managed
  Dokploy targets. Keep Dokploy auto deploy disabled for those targets.
- Managed remote targets may receive `DOCKER_IMAGE_REFERENCE=<repo>@<digest>`
  from the control plane so deploy execution can use an exact immutable image
  while local workflows keep the existing `DOCKER_IMAGE` + `DOCKER_IMAGE_TAG`
  contract.
- Direct Compose callers sanitize `DOCKER_IMAGE_REFERENCE` before invoking
  `docker compose` so local/testkit workflows keep using buildable image-name
  inputs even when shared runtime env files carry an immutable digest for
  remote execution.
- Native `odoo-control-plane` ship and promotion planning/execution no longer
  depend on `odoo-ai` request-export steps or repo-path delegation.
- When `platform ship` waits for deployment completion on compose-backed
  managed targets, it now runs the shared `platform update` workflow before
  final health verification so installed addon code/data changes are applied
  through one canonical upgrade path.
- `platform ship --no-wait` exits after triggering the deploy, so the post-
  deploy update and health verification steps do not run in that mode.
- Remote web startup uses `run_odoo_startup.py` to initialize missing modules
  when needed before launching the long-running server.
- Release-sensitive commands resolve env layers with collision mode `error`.
- For extracted tenants, manifest-backed local runtime env/config generation
  now lives in `odoo-devkit` via `platform runtime select --manifest ...` and
  `platform runtime inspect --manifest ...`.
- Manifest-backed remote `restore`/`bootstrap` for Dokploy-managed targets
  (`dev`, `testing`, `prod`) run through Dokploy schedule jobs triggered by the
  Dokploy API.
  Targets with deploy-server linkage use Dokploy `server` jobs; targets without
  linkage use Dokploy `dokploy-server` jobs. The platform no longer SSHes to
  Dokploy-managed targets. Before those schedule jobs run, platform syncs the
  generated workflow env into the Dokploy target and triggers a compose deploy
  so `script-runner` uses the workflow-specific image/runtime contract. If the
  previous matching Dokploy schedule was cancelled, the next retry clears the
  orphaned data-workflow lock before starting. Only the upstream source host
  copy inside
  `run_odoo_data_workflows.py` still uses SSH.
- `platform ship`, `platform rollback`, `platform status`, `platform info`,
  `platform doctor`, and `platform dokploy ...` helper commands require
  `target_id` / `target_name` from `platform/dokploy.toml` for managed remote
  targets. Name-based Dokploy API discovery is no longer part of the normal
  contract.
- `platform tui` allows wildcard or comma-separated fan-out only for read-only
  `status` and `info` workflows.

Command Patterns

- Use [@docs/tooling/platform-command-patterns.md](platform-command-patterns.md)
  for concrete examples, TUI usage, restore patterns, Dokploy helpers, and
  release workflow recipes.
- `platform dokploy inventory --output-file tmp/dokploy-inventory.json
--snapshot-dir tmp/dokploy-snapshots` captures a reusable live baseline of
  Dokploy projects, servers, and compose targets before destructive changes.

Related Docs

- [@docs/tooling/dokploy.md](dokploy.md) — remote target operations.
- [@docs/tooling/secrets.md](secrets.md) — env layering and secrets contract.
- [@docs/tooling/gpt-service-user.md](gpt-service-user.md) — `ODOO_KEY`
  restore provisioning behavior.
- [@docs/tooling/inspection.md](inspection.md) — JetBrains inspection setup.
- [@docs/control-plane-roadmap.md](../control-plane-roadmap.md) — long-term
  retirement plan for extracting responsibilities out of `odoo-ai`.
