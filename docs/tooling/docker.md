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
- Restore data: `uv run ops local restore <target>`
  - Targets: `opw`, `cm` (local stack names default to `opw-local`, `cm-local`)
  - Ensure `RESTORE_SSH_DIR` points at a host SSH directory so the base compose
    mounts it into the container for upstream access
  - When an upstream dump is unavailable, bootstrap with
    `uv run ops local init <target>`

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container

## Environment Variable Quick Reference

- `DEPLOY_COMPOSE_FILES` accepts colon- or comma-delimited values. Example:
  `DEPLOY_COMPOSE_FILES=docker/config/base.yaml:docker/config/opw-local.yaml`.
- `ODOO_UPDATE_MODULES` accepts a comma/colon list of modules to upgrade.
- `ODOO_AUTO_MODULES=AUTO` enables auto-upgrade based on local addons; set
  `LOCAL_ADDONS_DIRS=/volumes/addons` (colon/comma delimited) to control the
  search roots.
- `ODOO_ADDON_REPOSITORIES` accepts a comma-separated list of addon repos
  (cloned into `/opt/extra_addons/<repo>`). These are cloned with
  `GITHUB_TOKEN`.
  - Restore auto-updates skip enterprise addon repositories detected by the
    Odoo Enterprise Edition license (or a `web_enterprise` module under the
    repo root or `enterprise/` folder) inside `/opt/extra_addons`. Use
    `ODOO_UPDATE_MODULES` to explicitly include them if needed.

## Layered Compose Configuration

Local stacks use layered configs stored in `docker/config/`. The concise source
of truth is `docker/config/README.md`.

`docker-compose.override.yml` is local-only (ignored by git). Create it when
you need port bindings or live code mounts; see
`docs/workflows/multi-project.md` for an example.

The `uv run ops local up <target>` command reads `DEPLOY_COMPOSE_FILES` and
assembles the correct file order automatically.

## Bind-Mount Conventions

- Always set `ODOO_STATE_ROOT` for each stack. The deploy tooling derives
  `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and `ODOO_LOG_DIR` from that root
  (`filestore/`, `postgres/`, `logs/` subdirectories) before writing the merged
  `.env` that Compose and Pydantic consume. The merged compose env is stored at
  `${ODOO_STATE_ROOT}/.compose.env`. Stack env sources live in
  `docker/config/<project>-local.env` (tracked, non-secret). If the state root is
  not writable (remote stacks), the CLI falls back to
  `~/.odoo-ai/stack-env/<stack>.env`. If `ODOO_STATE_ROOT` is omitted (e.g.,
  local dev), the CLI defaults to `~/odoo-ai/${ODOO_PROJECT_NAME}/...`.
- `ODOO_DATA_HOST_DIR`, `ODOO_LOG_HOST_DIR`, and `ODOO_DB_HOST_DIR` are
  required for Compose. On remote hosts, create the target directories before
  the first deploy (for example,
  `mkdir -p /opt/odoo-ai/data/<stack>/{data,logs,postgres}`) so bind mounts do
  not fail.
- For Coolify deployments, use explicit bind mounts (`/host/path:/container`)
  instead of named volumes. Coolify rewrites named volumes per app, which
  bypasses `driver_opts` bindings. The Coolify apps point at
  `docker/coolify/<app>.yml` with hard-coded host paths so the bind mounts are
  enforced.
- Keep `ODOO_LOGFILE` pointed inside `/volumes/logs/` (e.g.
  `/volumes/logs/odoo.log`) so log rotation targets the bind-mounted directory.
- Remote hosts are managed in Coolify; local stacks should keep state under
  `~/odoo-ai/<stack>`.
