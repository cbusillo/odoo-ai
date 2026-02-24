---
title: Architecture Overview
---

Purpose

- Capture runtime topology and how local stacks relate to remote candidate
  environments.

When

- When diagnosing environment issues or onboarding.

## Runtime Topology

| Environment          | Location   | Deployment command                               |
| -------------------- | ---------- | ------------------------------------------------ |
| OPW local            | dev laptop | `uv run platform up --context opw --instance local --build` |
| CM local             | dev laptop | `uv run platform up --context cm --instance local --build`  |
| OPW dev/testing      | Coolify    | `uv run platform ship --context opw --instance <env>`       |
| CM dev/testing       | Coolify    | `uv run platform ship --context cm --instance <env>`        |
| OPW prod (candidate) | Coolify    | `uv run platform ship --context opw --instance prod`        |
| CM prod (candidate)  | Coolify    | `uv run platform ship --context cm --instance prod`         |
| OPW prod (live)      | legacy LXC | `opw-prod.shiny` (non-Docker)                    |

## Key points

- `uv run platform` is the canonical operator entrypoint for local and remote flows.
- `uv run ops` remains legacy compatibility only during migration.
- Local stacks use platform-generated runtime env under `.platform/env/` on top
  of `docker-compose.yml` + `docker/config/base.yaml` +
  `docker-compose.override.yml`.
- Coolify uses `docker/coolify/<app>.yml` plus environment variables defined in
  app settings. These compose files are standalone and are not generated from
  the local overlays.
- `opw-prod.shiny` remains the live production system until cutover; it is
  read-only and the data source for `opw-*` restores.
- Coolify prod apps track `opw-prod`/`cm-prod` branches and are treated as
  candidate prod during validation.
- Local state persistence is Docker named volumes per context/instance:
  `odoo-<context>-<instance>-{data,logs,db}`.
- Platform runtime control artifacts live in `.platform/`.
- `docker/scripts/install_prod_requirements.sh` and
  `docker/scripts/install_dev_requirements.sh` use `uv sync` with
  `/volumes/pyproject.toml` and `/volumes/uv.lock`.
- Restore flows rely on `RESTORE_SSH_DIR` so the base compose mounts the SSH
  directory for upstream access during
  `uv run platform run --context <target> --instance local --workflow restore`.

## Local deploy/restore

- Deploy: `uv run platform up --context <target> --instance local --build`
- Restore: `uv run platform run --context <target> --instance local --workflow restore`

## Application layers

- Base runtime image consumed by `odoo-ai`:
  `ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime`
- Public foundation image:
  `ghcr.io/cbusillo/odoo-docker:19.0-runtime`
- Custom addons: `/volumes/addons` (repo) and `/opt/extra_addons`
  (`ODOO_ADDON_REPOSITORIES` for non-enterprise extras).
- Enterprise addons: `/opt/enterprise` from
  `ghcr.io/cbusillo/odoo-enterprise-docker`.
- Integrations: Shopify active

## References

- Docker usage – `docs/tooling/docker.md`
- Local stack layering – `docker/config/README.md`
- Multi-project local config – `docs/workflows/multi-project.md`
- Restore entry point – `uv run platform run --context <target> --instance local --workflow restore`
