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
- Local stack env files run the web service under the PyCharm debugger.
  Create a **Python Debug Server** run configuration per stack:
  - Host: `0.0.0.0` (or `host.docker.internal`)
  - Port: `5678` (OPW) or `5679` (CM)
  - Path mappings: `/volumes/addons` → `$PROJECT_DIR$/addons`
  - Optional: enable “Suspend after connect” if you want to pause on startup
- The Debug Server starts listening before “Before launch” tasks run, so it is
  safe to keep `uv run ops local upgrade-restart <target>` as a pre-step; Odoo
  will reconnect to the debugger after the restart.
- For “always up to date” local debugging, keep the upgrade‑restart pre-step
  enabled so modules are upgraded on every Debug run.
- If you disable the upgrade‑restart pre-step for faster runs, use
  `uv run ops local upgrade <target>` when you change module schema/data
  (new fields, views, migrations).
