---
title: Architecture Overview
---

Purpose

- Capture the steady-state runtime topology and the boundaries between local
  stacks and Dokploy-managed environments.
- The long-term extraction of responsibilities out of `odoo-ai` into
  `odoo-devkit`, tenant/shared repos, and the private operator control plane
  lives in [@docs/control-plane-roadmap.md](control-plane-roadmap.md).

When

- When diagnosing environment issues or onboarding.

## Runtime Topology

- OPW local
  Location: dev laptop
  Deployment command:
  `uv --directory ../odoo-devkit run platform runtime up --manifest ../odoo-tenant-opw/workspace.toml --build`
- CM local
  Location: dev laptop
  Deployment command:
  `uv --directory ../odoo-devkit run platform runtime up --manifest ../odoo-tenant-cm/workspace.toml --build`
- OPW dev/testing
  Location: Dokploy
  Deployment command: `platform ship --context opw --instance <instance>`
- CM dev/testing
  Location: Dokploy
  Deployment command: `platform ship --context cm --instance <instance>`
- OPW prod
  Location: Dokploy
  Deployment command: `platform ship --context opw --instance prod`
- CM prod
  Location: Dokploy
  Deployment command: `platform ship --context cm --instance prod`

Use explicit context/instance flags in command invocations (for example
`--context opw --instance local`).

## Key points

- `uv run platform` is the canonical operator entrypoint for local and remote
  flows.
- `platform/stack.toml` is the source of truth for valid contexts and
  instance names.
- Extracted-tenant local runtime ownership now lives in `odoo-devkit` via
  manifest-backed `platform runtime ... --manifest <workspace.toml>` commands.
- `odoo-ai` no longer owns repo-local local-runtime lifecycle commands such as
  `select`, `up`, `down`, `logs`, `build`, `inspect`, or `odoo-shell`; those
  names remain only as retirement shims that fail closed with migration
  guidance.
- `dev`, `testing`, and `prod` are Dokploy-managed remote instances and should
  be managed with Dokploy release flows (`ship`, `rollback`, `gate`, and
  `platform dokploy ...` helpers).
- Local stacks use platform-generated runtime env under `.platform/env/`
  on top of `docker-compose.yml` + `platform/compose/base.yaml` +
  `docker-compose.override.yml`.
- Dokploy manages remote compose/application targets from its control plane;
  local overlays are only for host-local runtime.
- Dokploy prod apps track `opw-prod`/`cm-prod` branches.
- Local state persistence is Docker named volumes per context/instance:
  `odoo-<context>-<instance>-{data,logs,db}`.
- Platform runtime control artifacts live in `.platform/`.
- Image build layers preserve the inherited `/venv` from the upstream image
  chain. `odoo-ai` installs project dependencies additively from its lockfile
  instead of recreating or destructively re-syncing the base environment;
  operators do not call the install scripts directly.
- Data workflows rely on `DATA_WORKFLOW_SSH_DIR` so the base compose mounts
  the SSH directory for upstream access during
  `uv --directory ../odoo-devkit run platform runtime restore --manifest ../odoo-tenant-<target>/workspace.toml`.
- That SSH directory must include both the private key and trusted
  `known_hosts` entries needed for upstream access.

## Local deploy/restore

- Deploy: `uv --directory ../odoo-devkit run platform runtime up --manifest ../odoo-tenant-<target>/workspace.toml --build`
- Restore: `uv --directory ../odoo-devkit run platform runtime restore --manifest ../odoo-tenant-<target>/workspace.toml`

## Application layers

- Base runtime image consumed by `odoo-ai`:
  private Enterprise runtime image configured outside public repos
- Base devtools image consumed by local `odoo-ai` builds:
  private Enterprise devtools image configured outside public repos
- Public foundation image:
  `ghcr.io/cbusillo/odoo-docker:19.0-runtime`
- Public devtools foundation image:
  `ghcr.io/cbusillo/odoo-docker:19.0-devtools`
- Custom addons: `/opt/project/addons` for root wrapper addons plus discovered
  nested addon buckets such as `/opt/project/addons/shared` and
  `/opt/project/addons/cm`, alongside `/opt/extra_addons`
  (`ODOO_ADDON_REPOSITORIES` for non-enterprise extras).
- Enterprise addons: `/opt/enterprise` from
  the private Enterprise layer image.
- Dev-only addon path shaping lives upstream in the image chain. `odoo-docker`
  devtools exposes `/odoo`, `/opt/project/addons`, and `/opt/extra_addons`,
  and the private Enterprise layer appends `/opt/enterprise`. `odoo-ai` keeps
  `/opt/project` as a real directory in the image. Both production and
  development targets bake `/opt/project/addons` at build time; runtime env
  generation expands nested addon grouping directories under that root so Odoo
  sees wrapper addons and grouped tenant/shared addons without a flat top-level
  addon tree. Local workflows that need live addon editing must override that
  path explicitly with a bind mount.
  `/volumes/pyproject.toml` and `/volumes/uv.lock` point at the root lockfiles,
  and local devtools images link `/opt/project/tools` to the `/volumes/tools`
  bind mount used by testkit.
- Integrations: Shopify active

## References

- Docker usage – @docs/tooling/docker.md
- Local stack layering – `platform/config/README.md`
- Multi-project local config – @docs/workflows/multi-project.md
- Long-term control-plane target state – @docs/control-plane-roadmap.md
- Restore entry point -
  `uv --directory ../odoo-devkit run platform runtime restore --manifest ../odoo-tenant-<target>/workspace.toml`
