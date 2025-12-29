---
title: Architecture Overview
---


This page captures the current runtime topology and how local stacks relate to
Coolify-managed environments.

## Runtime Topology

| Environment     | Location         | Deployment                            |
|-----------------|------------------|---------------------------------------|
| OPW local       | developer laptop | `uv run up --stack opw-local`         |
| CM local        | developer laptop | `uv run up --stack cm-local`          |
| OPW dev/testing | Coolify + Docker | Coolify UI                            |
| CM dev/testing  | Coolify + Docker | Coolify UI                            |

## Key points

- Local stacks use `docker/config/*.env` and `docker/config/*.yaml` overlays.
  Coolify uses `docker-compose.yml` plus environment variables defined in the UI.
- Bind mounts are used for state; set `ODOO_STATE_ROOT` per local stack so
  `filestore/`, `postgres/`, and `logs/` stay isolated.
- `docker/scripts/install_prod_requirements.sh` and
  `docker/scripts/install_dev_requirements.sh` use `uv sync` with
  `/volumes/pyproject.toml` and `/volumes/uv.lock`.
- Use `docker/config/_restore_ssh_volume.yaml` when running
  `uv run restore` locally so the container can reach upstream.

## Local deploy/restore

- Deploy: `uv run up --stack <stack>`
- Restore: `uv run restore <stack>`

## Application layers

- Base Odoo: `ghcr.io/adomi-io/odoo:18.0`
- Custom addons: `/volumes/addons` (repo), `/volumes/extra_addons`
  (`ODOO_ADDON_REPOSITORIES`), and `/volumes/enterprise` (private mirror)
- Integrations: Shopify active

## References

- Docker usage – `docs/tooling/docker.md`
- Local stack layering – `docker/config/README.md`
- Multi-project local config – `docs/workflows/multi-project.md`
- Restore entry point – `uv run restore` (`tools/restore_shortcuts.py`)
- Deploy CLI – `uv run deploy` (`tools/deployer/cli.py`)
