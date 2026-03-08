---
title: Docker Usage
---


Purpose

- Provide standard container operations for local Odoo stacks.

When

- Any time you need logs, restarts, or shell access to containers.

Common operations (CLI)

- Status: `docker ps --format 'table {{.Names}}\t{{.Status}}'`
- Logs: `docker logs --tail=200 <container>` (add `-f` to follow)
- Restart: `docker restart <container>`
- Shell: `docker exec -it <container> bash`

Odoo-specific

- Web logs: `docker logs --tail=300 ${ODOO_PROJECT_NAME}-web-1`
- Restart services:
  `docker restart ${ODOO_PROJECT_NAME}-web-1 ${ODOO_PROJECT_NAME}-script-runner-1`
- Update module:
  `docker exec ${ODOO_PROJECT_NAME}-script-runner-1 /odoo/odoo-bin -u <module> --stop-after-init`
- Restore data:
  `uv run platform run --context <target> --instance local --workflow restore`
  Targets: `opw`, `cm`.
  Ensure `RESTORE_SSH_DIR` points at a host SSH directory so the base compose
  mounts it into the container for upstream access.
  When an upstream dump is unavailable, bootstrap with
  `uv run platform run --context <target> --instance local --workflow init`.

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container
- `docker/scripts/run_odoo_with_debug.sh` is a local debug launcher only.
  It bypasses bootstrap safeguards (`run_odoo_bootstrap.py`) such as DB
  readiness checks, restore-lock waiting, and initialization gates.

## Environment Variable Quick Reference

- `ODOO_INSTALL_MODULES` accepts a comma/colon list of modules to install on
  init/restore.
- `ODOO_UPDATE_MODULES` accepts a comma/colon list of modules to upgrade; set
  `ODOO_UPDATE_MODULES=AUTO` to update all installed local addons.
- `LOCAL_ADDONS_DIRS=/opt/project/addons` (colon/comma delimited) controls the
  auto-update search roots.
- `ODOO_BASE_RUNTIME_IMAGE` and `ODOO_BASE_DEVTOOLS_IMAGE` set the runtime and
  devtools base images for `docker/Dockerfile`.
  For the three-layer strategy, these should point to private enterprise image
  tags (for example `ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime` and
  `ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools`), ideally pinned by
  digest in promoted environments.
- For private GHCR base images, `platform` commands perform a registry login
  preflight before build/restore. Provide either:
  - `GHCR_TOKEN` (preferred) or `GITHUB_TOKEN`
  - `GHCR_USERNAME` (falls back to image owner / `GITHUB_ACTOR`)
  Tokens must include package read access (`read:packages`) for the private
  image package.
- Full tag and promotion contracts are documented in
  [@docs/tooling/image-contracts.md](image-contracts.md).
- `ODOO_ADDON_REPOSITORIES` accepts a comma-separated list of addon repos
  (downloaded into `/opt/extra_addons/<repo>` as GitHub source archives by the
  inherited `odoo-fetch-addons.sh` helper from the base image).
  The build consumes `GITHUB_TOKEN` through a BuildKit secret so tokens are not
  persisted in image layers.
- Enterprise addons should come from the private base image layer
  (`/opt/enterprise`) rather than `ODOO_ADDON_REPOSITORIES`.
- Upgrade-only repositories such as OpenUpgrade are not auto-added to every
  build. Platform derives them for workflows that set `OPENUPGRADE_ENABLED`, so
  steady-state builds stay clean while restore/openupgrade flows still fetch the
  required addon repo explicitly.
- When OpenUpgrade is enabled, platform also sets
  `ODOO_PYTHON_SYNC_SKIP_ADDONS=openupgrade_framework,openupgrade_scripts,openupgrade_scripts_custom`
  so those addon paths are available to Odoo without trying to package them
  into `/venv`.
- `odoo-ai` keeps the remaining OpenUpgrade-specific Python support locally:
  when `OCA/OpenUpgrade` is present in the external addon repo list, the image
  also installs `openupgradelib==3.12.0` into `/venv`.

## Layered Compose Configuration

Local stacks use layered configs under `platform/config/` and
`platform/compose/`. The concise source of truth is `platform/config/README.md`.

`docker-compose.override.yml` is local-only (ignored by git). Create it when
you need port bindings or live code mounts; see
@docs/workflows/multi-project.md for an example.

Platform local lifecycle commands (`up`, `build`, `down`, `logs`) use the
platform runtime env (`.platform/env/<context>.<instance>.env`) and base compose
file stack:

```text
docker-compose.yml
→ platform/compose/base.yaml
→ docker-compose.override.yml (if present)
```

## Persistence Notes

- Local platform workflows use named volumes per context/instance and
  `.platform/state/<context>-<instance>/` for generated runtime artifacts.
- Dokploy-managed targets keep remote persistence in Dokploy target settings.
  Use `uv run platform dokploy env-get|env-set|env-unset` for managed env
  updates rather than ad-hoc scripts.
- Keep `ODOO_LOGFILE` under `/volumes/logs/` (for example
  `/volumes/logs/odoo.log`) so logs remain in persisted storage.
