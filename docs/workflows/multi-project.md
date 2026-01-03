---
title: Multi-Project Configuration (Local Dev)
---

Purpose

- Run multiple isolated stacks locally (OPW + Cell Mechanic) using layered
  Docker Compose configs.
- Remote environments are managed in Coolify and do not use the overlays in
  `docker/config/`.

When

- When running multiple local stacks on the same host.

Local stacks

| Stack       | Purpose      | Ports           | Config source   |
|-------------|--------------|-----------------|-----------------|
| `opw-local` | OPW dev      | 8069/8072/15432 | `opw-local.env` |
| `cm-local`  | CM isolation | 9069/9072/9432  | `cm-local.env`  |

Quick flow

1. Update the stack env file (`docker/config/opw-local.env`).

2. Start the stack (add `--build` if you need a rebuild):

   ```bash
   uv run ops local up opw --build
   ```

3. (Optional) Restore upstream data:

   ```bash
   uv run ops local restore opw
   ```

Notes

- Layer order and env merge rules are documented in `docker/config/README.md`.
- Create a local `docker-compose.override.yml` to expose ports and mount the
  repo for live-editing. Example:

  ```yaml
  services:
    web:
      ports:
        - "${ODOO_WEB_HOST_PORT:-8069}:8069"
        - "${ODOO_LONGPOLL_HOST_PORT:-8072}:8072"
    database:
      ports:
        - "${ODOO_DB_HOST_PORT:-5432}:5432"
    script-runner:
      volumes:
        - ./docker/scripts:/volumes/scripts
        - ./addons:/volumes/addons
        - ./pyproject.toml:/opt/project/pyproject.toml:ro
        - ./addons:/opt/project/addons
      environment:
        - ODOO_ADDON_REPOSITORIES=
  ```

- Use unique `ODOO_STATE_ROOT` per stack to avoid sharing filestore/postgres.
- Switch stacks by stopping one (`uv run ops local down cm`) before
  starting the other.
