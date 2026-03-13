---
title: Architecture Overview
---

Purpose

- Capture the steady-state runtime topology and the boundaries between local
  stacks and Dokploy-managed environments.

When

- When diagnosing environment issues or onboarding.

## Runtime Topology

| Environment     | Location   | Deployment command                                  |
|-----------------|------------|-----------------------------------------------------|
| OPW local       | dev laptop | `platform up --context opw --instance local`        |
| CM local        | dev laptop | `platform up --context cm --instance local`         |
| OPW dev/testing | Dokploy    | `platform ship --context opw --instance <instance>` |
| CM dev/testing  | Dokploy    | `platform ship --context cm --instance <instance>`  |
| OPW prod        | Dokploy    | `platform ship --context opw --instance prod`       |
| CM prod         | Dokploy    | `platform ship --context cm --instance prod`        |

Use explicit context/instance flags in command invocations (for example
`--context opw --instance local`).

## Key points

- `uv run platform` is the canonical operator entrypoint for local and remote
  flows.
- `platform/stack.toml` is the source of truth for valid contexts and
  instance names.
- Local runtime lifecycle and mutating workflows (`select`, `up`, `down`,
  `logs`, `build`, `run`, `init`, `update`, `openupgrade`, `inspect`) are
  host-local operations and require `--instance local`.
- `dev`, `testing`, and `prod` are Dokploy-managed remote instances and should
  be managed with Dokploy release flows (`ship`, `rollback`, `gate`,
  `promote`, and `platform dokploy ...` helpers).
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
  `uv run platform restore --context <target> --instance local`.
- That SSH directory must include both the private key and trusted
  `known_hosts` entries needed for upstream access.

## Local deploy/restore

- Deploy: `uv run platform up --context <target> --instance local --build`
- Restore: `uv run platform restore --context <target> --instance local`

## Application layers

- Base runtime image consumed by `odoo-ai`:
  `ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime`
- Base devtools image consumed by local `odoo-ai` builds:
  `ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools`
- Public foundation image:
  `ghcr.io/cbusillo/odoo-docker:19.0-runtime`
- Public devtools foundation image:
  `ghcr.io/cbusillo/odoo-docker:19.0-devtools`
- Custom addons: `/volumes/addons` (repo) and `/opt/extra_addons`
  (`ODOO_ADDON_REPOSITORIES` for non-enterprise extras).
- Enterprise addons: `/opt/enterprise` from
  `ghcr.io/cbusillo/odoo-enterprise-docker`.
- Dev-only addon path shaping lives upstream in the image chain:
  - `odoo-docker` devtools exposes `/odoo`, `/opt/project/addons`, and
    `/opt/extra_addons`
  - `odoo-enterprise-docker` devtools appends `/opt/enterprise`
  - `odoo-ai` does not own `.pth` path shaping
- Integrations: Shopify active

## References

- Docker usage – @docs/tooling/docker.md
- Local stack layering – `platform/config/README.md`
- Multi-project local config – @docs/workflows/multi-project.md
- Restore entry point –
  `uv run platform restore --context <target> --instance local`
