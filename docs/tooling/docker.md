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
- Restore data: `uv run restore-from-upstream --stack opw-testing` (swap `opw-testing` for `opw-dev` or `local`)
    - Ensure the stack mounts an SSH directory (`RESTORE_SSH_DIR`) so the script can reach `opw-prod.shiny` (defaults to
      `/root/.ssh` remotely, `$HOME/.ssh` locally).

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container

Note

- Using the Docker MCP tools? See docs/tooling/docker-mcp.md for parameter shapes and examples (JSON for environment,
  ports, volumes).

## Bind-Mount Conventions

- Always set `ODOO_STATE_ROOT` for each stack. The deploy tooling derives `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and
  `ODOO_LOG_DIR`
  from that root (`filestore/`, `postgres/`, `logs/` subdirectories) before writing the merged `.env` that Compose and
  Pydantic consume. Stack env sources live in `docker/config/<stack>.env` (create them locally; they’re git-ignored). If
  `ODOO_STATE_ROOT` is omitted (e.g., local dev), the CLI defaults to `${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`.
- Keep `ODOO_LOGFILE` pointed inside `/volumes/logs/` (e.g. `/volumes/logs/odoo.log`) so log rotation targets the
  bind-mounted directory.
- Remote hosts should pair `ODOO_STATE_ROOT=/opt/odoo-ai/data/<stack>` with
  `DEPLOY_REMOTE_STACK_PATH=/opt/odoo-ai/repos/<stack>`
  to mirror the documented layout; don’t drop persistent data into the git checkout.
