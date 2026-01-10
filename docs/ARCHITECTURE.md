---
title: Architecture Overview
---

Purpose

- Capture runtime topology and how local stacks relate to Coolify-managed
  environments.

When

- When diagnosing environment issues or onboarding.

## Runtime Topology

| Environment          | Location   | Deployment                         |
|----------------------|------------|------------------------------------|
| OPW local            | dev laptop | `uv run ops local up opw --build`  |
| CM local             | dev laptop | `uv run ops local up cm --build`   |
| OPW dev/testing      | Coolify    | Coolify UI                         |
| CM dev/testing       | Coolify    | Coolify UI                         |
| OPW prod (candidate) | Coolify    | app `opw-prod`                     |
| CM prod (candidate)  | Coolify    | app `cm-prod`                      |
| OPW prod (live)      | legacy LXC | `opw-prod.shiny` (non-Docker)      |

## Key points

- Local stacks use `docker/config/*.env` and `docker/config/*.yaml` overlays.
  Coolify uses `docker/config/coolify.yml` plus environment variables defined
  in the UI.
- `opw-prod.shiny` remains the live production system until cutover; it is
  read-only and the data source for `opw-*` restores.
- Coolify prod apps track `opw-prod`/`cm-prod` branches and are treated as
  candidate prod during validation.
- Bind mounts are used for state; set `ODOO_STATE_ROOT` per local stack so
  `filestore/`, `postgres/`, and `logs/` stay isolated.
- `docker/scripts/install_prod_requirements.sh` and
  `docker/scripts/install_dev_requirements.sh` use `uv sync` with
  `/volumes/pyproject.toml` and `/volumes/uv.lock`.
- Restore flows rely on `RESTORE_SSH_DIR` so the base compose mounts the SSH
  directory for upstream access during `uv run ops local restore <target>`.

## Local deploy/restore

- Deploy: `uv run ops local up <target> --build`
- Restore: `uv run ops local restore <target>`

## Application layers

- Base Odoo: `ghcr.io/adomi-io/odoo:19.0`
- Custom addons: `/volumes/addons` (repo) and `/opt/extra_addons`
  (`ODOO_ADDON_REPOSITORIES`, including the enterprise addons)
- Integrations: Shopify active

## References

- Docker usage – `docs/tooling/docker.md`
- Local stack layering – `docker/config/README.md`
- Multi-project local config – `docs/workflows/multi-project.md`
- Restore entry point – `uv run ops local restore <target>`
