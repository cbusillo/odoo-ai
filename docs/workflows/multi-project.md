---
title: Multi-Project Configuration (Local Dev)
---

Purpose

- Run multiple isolated stacks locally (OPW + CM/Connect Motors) using layered
  Docker Compose configs.
- Remote environments are managed in Dokploy and do not use the overlays in
  `platform/config/` and `platform/compose/`.

When

- When running multiple local stacks on the same host.

Local stacks

| Stack       | Purpose      | Ports           | Config source   |
|-------------|--------------|-----------------|-----------------|
| `opw-local` | OPW dev      | 8069/8072/15432 | platform config |
| `cm-local`  | CM isolation | 9069/9072/25432 | platform config |

`platform config` means `platform/stack.toml` and `platform/secrets.toml`.

Quick flow

1. Set context/instance values in `platform/secrets.toml` and/or `.env`.

2. Select and inspect the runtime env for the stack:

   ```bash
   uv run platform select --context opw --instance local --dry-run
   uv run platform select --context opw --instance local
   ```

3. Start the stack (add `--build` if you need a rebuild):

   ```bash
   uv run platform up --context opw --instance local --build
   ```

4. (Optional) Restore upstream data:

   ```bash
   uv run platform restore --context opw --instance local
   ```

Notes

- Layer order and env merge rules are documented in `platform/config/README.md`.
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
        - ./pyproject.toml:/opt/project/pyproject.toml:ro
        - ./addons:/opt/project/addons
      environment:
        - ODOO_ADDON_REPOSITORIES=
  ```

- Use unique `ODOO_STATE_ROOT` per stack to avoid sharing filestore/postgres.
- You can run both local stacks at once when host resources allow it.
- Local stack env files run the web service under the PyCharm debugger.
  Create a **Python Debug Server** run configuration per stack:
  - Host: `0.0.0.0` (or `host.docker.internal`)
  - Port: `5678` (OPW) or `5679` (CM)
  - Path mappings: `/opt/project/addons` → `$PROJECT_DIR$/addons`
  - Optional: enable “Suspend after connect” if you want to pause on startup
- The Debug Server starts listening before “Before launch” tasks run, so it is
  safe to keep
  `uv run platform run --context <target> --instance local --workflow update`
  as a pre-step; Odoo will reconnect to the debugger after the restart.
- For “always up to date” local debugging, keep the upgrade‑restart pre-step
  enabled so modules are upgraded on every Debug run.
- If you disable the update pre-step for faster runs, use
  `uv run platform run --context <target> --instance local --workflow update`
  when you change module schema/data
  (new fields, views, migrations).
