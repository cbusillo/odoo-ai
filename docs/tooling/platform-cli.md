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
- `tools/platform/release_workflows.py` — release gate and promote logic.
- `platform/stack.toml` — context and instance contract.
- `platform/dokploy.toml` — remote target branch/domain contract.
- `platform/secrets.toml` (optional, local) — layered secret/env overrides.

Operator Contract

- `local` is the only host runtime on this machine.
- Use `platform init`, `platform build`, `platform up`,
  `platform down`, `platform logs`, `platform inspect`, and
  `platform odoo-shell` only with `--instance local`.
- Treat `dev`, `testing`, and `prod` as Dokploy-managed remote targets.
  Use `platform ship`, `platform update`, `platform rollback`, `platform gate`,
  `platform promote`, `platform restore`, and `platform bootstrap` there.
- `platform ship` is the non-destructive remote deploy/restart path.
- `platform rollback` currently supports Dokploy application targets only.
  Compose targets must use Dokploy UI rollback controls.
- `platform restore` is the destructive upstream-data replacement path.
- `platform bootstrap` is the destructive fresh-start rebuild path.
- `platform init` remains a local-only module initialization pass for an
  existing database.
- `platform update` applies module updates against the selected local runtime
  or compose-backed managed runtime.
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

- Local lifecycle: `select`, `info`, `status`, `doctor`, `build`, `up`,
  `down`, `logs`, `inspect`, `odoo-shell`.
- Data workflows: `restore`, `bootstrap`.
- Runtime workflows: `run`, `init`, `update`, `openupgrade`.
- Validation scenarios: `validate ...`.
- Remote release: `ship`, `rollback`, `gate`, `promote`, and
  `platform dokploy ...` helpers.
- Dokploy inventory: `platform dokploy inventory` for project/server/target
  snapshots before teardown, recreation, or reconciliation work.
- Secrets/env introspection: `platform secrets explain`.
- Interactive launcher: `platform tui`.

Behavior Highlights

- `platform doctor` is read-only and spans both local runtime diagnostics and
  Dokploy target diagnostics.
- `platform ship` fails closed on dirty tracked files. Prefer a clean worktree
  plus `--source-ref HEAD` for surgical remote testing.
- `platform promote` follows the same clean-tree policy as `platform ship` and
  accepts `--allow-dirty` only as an explicit override.
- `platform promote` now treats `odoo-control-plane` as the first compatibility
  owner for live promotion orchestration. The wrapper fails closed if the
  sibling control-plane repo is missing or misconfigured instead of silently
  falling back to legacy in-repo ownership.
- `platform ship` now follows the same ownership rule: the public command is a
  fail-closed wrapper into `odoo-control-plane`, while the old execution path
  survives only as an internal compatibility worker for control-plane
  delegation during transition.
- `platform ship` is the only supported remote deployment trigger for managed
  Dokploy targets. Keep Dokploy auto deploy disabled for those targets.
- When `platform ship` waits for deployment completion on compose-backed
  managed targets, it now runs the shared `platform update` workflow before
  final health verification so installed addon code/data changes are applied
  through one canonical upgrade path.
- `platform ship --no-wait` exits after triggering the deploy, so the post-
  deploy update and health verification steps do not run in that mode.
- Remote web startup uses `run_odoo_startup.py` to initialize missing modules
  when needed before launching the long-running server.
- Release-sensitive commands resolve env layers with collision mode `error`.
- `platform export-artifact-identity` is a read-only bridge for the future
  private control plane: it renders the typed artifact identity manifest from
  current runtime inputs plus explicit build outputs such as Enterprise digest
  and final image digest.
- `platform handoff-artifact-identity` is the write-side companion for that
  contract: it generates the same typed manifest and persists it into
  `odoo-control-plane`.
- `platform export-promotion-record` is the matching read-only bridge for the
  current compatibility promote workflow: it renders the typed promotion
  record from current target definitions, healthcheck settings, and explicit
  release evidence overrides such as backup evidence or deployment status.
- `platform export-ship-request` is the read-only compatibility contract for a
  future direct `ship` handoff: it renders the typed deploy request that the
  control plane will eventually own directly, without moving live `ship`
  ownership yet.
- `platform restore` and `platform bootstrap` use the same generated runtime env
  contract as `platform select`.
- `platform select` writes both `.platform/env/<context>.<instance>.env` and
  `.platform/ide/<context>.<instance>.odoo.conf`.
- Remote `restore`/`bootstrap` for Dokploy-managed targets (`dev`, `testing`,
  `prod`) run through Dokploy schedule jobs triggered by the Dokploy API.
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
  plan for moving deploy/control-plane concerns out of `odoo-ai`.
