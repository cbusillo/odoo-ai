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
    - Available stacks: `opw-local`, `opw-dev`, `opw-testing`, `cm-local`
    - Ensure the stack mounts an SSH directory (`RESTORE_SSH_DIR`) so the script can reach `opw-prod.shiny` (defaults to
      `/root/.ssh` remotely, `$HOME/.ssh` locally)
    - When an upstream dump is unavailable, bootstrap an empty database with
      `uv run python tools/docker_runner.py --stack <stack-name> --bootstrap-only`

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container

Note

- Using the Docker MCP tools? See docs/tooling/docker-mcp.md for parameter shapes and examples (JSON for environment,
  ports, volumes).

## Environment Variable Quick Reference

- `DEPLOY_COMPOSE_FILES` accepts colon- or comma-delimited values. Example:
  `DEPLOY_COMPOSE_FILES=docker-compose.yml:docker-compose.override.yml:docker/config/opw-testing.yaml`.
- `ODOO_UPDATE=AUTO` discovers modules under `LOCAL_ADDONS_DIRS` or `ODOO_ADDONS_PATH`; set
  `LOCAL_ADDONS_DIRS=/volumes/addons/opw:/volumes/enterprise` (colon/comma delimited) to control the search.

## Layered Compose Configuration

The deploy tooling follows a layered configuration pattern:

1. **Base layer** (`docker-compose.yml`) – defines core service structure and defaults
2. **Override layer** (`docker-compose.override.yml`) – local development conveniences
3. **Project layer** (`docker/config/{project}.yaml`) – project-specific settings (e.g., `opw-local.yaml`,
   `cm-local.yaml`)
4. **Variant layers** (optional) – additional overlays like `_restore_ssh_volume.yaml`

Files are applied in order; later files override earlier settings. Control the compose file list via
`DEPLOY_COMPOSE_FILES` in your stack's `.env`:

```bash
# Example: opw-testing.env
DEPLOY_COMPOSE_FILES=docker-compose.yml:docker-compose.override.yml:docker/config/_restore_ssh_volume.yaml:docker/config/opw-testing.yaml
```

Or rely on the default pattern (base → override → `docker/config/{stack-name}.yaml`):

```bash
# Minimal stack config - uses defaults
ODOO_PROJECT_NAME=opw-local
ODOO_STATE_ROOT=${HOME}/odoo-ai/opw-local
```

Example manual invocation showing file order:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/_restore_ssh_volume.yaml \
  -f docker/config/opw-testing.yaml \
  up -d
```

The `uv run deploy deploy --stack <name>` command automatically reads `DEPLOY_COMPOSE_FILES` and assembles the correct
order.

## Bind-Mount Conventions

- Always set `ODOO_STATE_ROOT` for each stack. The deploy tooling derives `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and
  `ODOO_LOG_DIR` from that root (`filestore/`, `postgres/`, `logs/` subdirectories) before writing the merged `.env`
  that Compose and Pydantic consume. Stack env sources live in `docker/config/<stack>.env` (create them locally; they're
  git-ignored). If `ODOO_STATE_ROOT` is omitted (e.g., local dev), the CLI defaults to
  `${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`.
- Keep `ODOO_LOGFILE` pointed inside `/volumes/logs/` (e.g. `/volumes/logs/odoo.log`) so log rotation targets the
  bind-mounted directory.
- Remote hosts should pair `ODOO_STATE_ROOT=/opt/odoo-ai/data/<stack>` with
  `DEPLOY_REMOTE_STACK_PATH=/opt/odoo-ai/repos/<stack>` to mirror the documented layout; don't drop persistent data into
  the git checkout.
