# Docker Usage

Common operations (CLI)

- Status: `docker ps --format 'table {{.Names}}\t{{.Status}}'`
- Logs: `docker logs --tail=200 <container>` (add `-f` to follow)
- Restart: `docker restart <container>`
- Shell: `docker exec -it <container> bash`

Odoo-specific

- Web logs: `docker logs --tail=300 ${ODOO_PROJECT_NAME}-web-1`
- Restart services: `docker restart ${ODOO_PROJECT_NAME}-web-1 ${ODOO_PROJECT_NAME}-shell-1`
- Update module: `docker exec ${ODOO_PROJECT_NAME}-script-runner-1 /odoo/odoo-bin -u <module> --stop-after-init`
- Restore data: `uv run restore-from-upstream --stack <stack-name>`
    - Available stacks: `opw-local`, `cm-local`
    - Ensure the stack mounts an SSH directory (`RESTORE_SSH_DIR`) so the
      container can reach the upstream host
    - When an upstream dump is unavailable, bootstrap an empty database with
      `uv run python tools/docker_runner.py --stack <stack-name> --bootstrap-only`

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container

## Environment Variable Quick Reference

- `DEPLOY_COMPOSE_FILES` accepts colon- or comma-delimited values. Example:
  `DEPLOY_COMPOSE_FILES=docker-compose.yml:docker-compose.override.yml:docker/config/base.yaml:docker/config/opw.yaml`.
- `ODOO_UPDATE=AUTO` discovers modules under `LOCAL_ADDONS_DIRS` or `ODOO_ADDONS_PATH`; set
  `LOCAL_ADDONS_DIRS=/volumes/addons/opw:/volumes/enterprise` (colon/comma delimited) to control the search.

## Layered Compose Configuration

Local stacks use layered configs stored in `docker/config/`. The concise source
of truth is `docker/config/README.md`.

The `uv run deploy deploy --stack <name>` command reads `DEPLOY_COMPOSE_FILES`
and assembles the correct file order automatically.

## Bind-Mount Conventions

- Always set `ODOO_STATE_ROOT` for each stack. The deploy tooling derives `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and
  `ODOO_LOG_DIR` from that root (`filestore/`, `postgres/`, `logs/` subdirectories) before writing the merged `.env`
  that Compose and Pydantic consume. Stack env sources live in `docker/config/<stack>.env` (create them locally; they're
  git-ignored). If `ODOO_STATE_ROOT` is omitted (e.g., local dev), the CLI defaults to
  `${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`.
- Keep `ODOO_LOGFILE` pointed inside `/volumes/logs/` (e.g. `/volumes/logs/odoo.log`) so log rotation targets the
  bind-mounted directory.
- Remote hosts are managed in Coolify; local stacks should keep state under
  `${HOME}/odoo-ai/<stack>`.
