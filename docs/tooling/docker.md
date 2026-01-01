---
title: Docker Usage
---


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
- Restore data: `uv run stack up --stack <stack-name> --restore`
  - Available stacks: `opw-local`, `cm-local`, `opw-dev`, `opw-testing`,
    `cm-dev`, `cm-testing`
  - Ensure the stack mounts an SSH directory (`RESTORE_SSH_DIR`) so the
    container can reach the upstream host
  - When an upstream dump is unavailable, bootstrap with
    `uv run stack up --stack <stack-name> --init`

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

## Layered Compose Configuration

Local stacks use layered configs stored in `docker/config/`. The concise source
of truth is `docker/config/README.md`.

`docker-compose.override.yml` is local-only (ignored by git). Create it when
you need port bindings or live code mounts; see
`docs/workflows/multi-project.md` for an example.

The `uv run stack up --stack <name>` command reads `DEPLOY_COMPOSE_FILES` and
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
- Keep `ODOO_LOGFILE` pointed inside `/volumes/logs/` (e.g.
  `/volumes/logs/odoo.log`) so log rotation targets the bind-mounted directory.
- Remote hosts are managed in Coolify; local stacks should keep state under
  `~/odoo-ai/<stack>`.
