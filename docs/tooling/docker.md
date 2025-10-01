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
    - Before running, ensure `RESTORE_SSH_DIR` points at an SSH directory with access to `opw-prod.shiny` (defaults to
      `/root/.ssh` on the remote host). For local restores set `RESTORE_SSH_DIR=$HOME/.ssh`.

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container

Note

- Using the Docker MCP tools? See docs/tooling/docker-mcp.md for parameter shapes and examples (JSON for environment,
  ports, volumes).
