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

Tips

- Filter containers: `docker ps | grep odoo`
- Stream long logs with `-f`, then Ctrl+C
- Prefer updates via script-runner; avoid mutating the web container
