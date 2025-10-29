Title: Cell Mechanic Dev Database

Use this recipe when you want to work on the `cell_mechanic` addon in isolation without disturbing the default OPW
stack. It defines a dedicated database, filestore, and port mappings and integrates cleanly with PyCharm’s Docker
compose run configurations.

## 1. Prepare environment overrides

1. Copy `docker/config/cm-dev.env.example` to `docker/config/cm-dev.env`.
2. Adjust values as needed:
    - `COMPOSE_PROJECT_NAME` controls the Docker project slug; the checked-in default is `cmdev` so container names are
      `cmdev-web-1`, `cmdev-database-1`, etc.
    - `ODOO_DB_NAME` & `ODOO_PROJECT_NAME` control the database name and Odoo config label inside the container.
    - `ODOO_UPDATE` defaults to `cell_mechanic`; add additional module names if you want them auto-installed.
    - Port variables (`ODOO_WEB_HOST_PORT`, `ODOO_LONGPOLL_HOST_PORT`, `ODOO_DB_HOST_PORT`) are already offset from the
      main stack (`9069/9072/9432`). Change them if those ports are occupied locally.

## 2. One-click init via run configs

- **OPW Local Init** rebuilds the legacy OPW stack (unchanged from before).
- **CM Local Init** lives at `.idea/runConfigurations/CM_Local_Init.run.xml`. It wipes `~/odoo-ai/cm-local`, redeploys
  `cm-local`, waits for Postgres to finish booting, creates the empty `cm` database, installs
  `cm_custom, external_ids, hr_employee_name_extended, disable_odoo_online, discuss_record_links`, and leaves
  web/script-runner/database running on ports `9069/9072/9432`. The fresh database uses the default `admin`/`admin`
  credentials—change them on first login.

## 3. Restore the cm database (optional)

If you need a fresh snapshot from upstream, run the restore helper against the new env file:

```bash
uv run restore-from-upstream --env-file docker/config/cm-dev.env
```

The script will create the database, sync the filestore under `${ODOO_STATE_ROOT}`, and apply `ODOO_UPDATE` modules.

## 4. Start the Docker services

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/cm-dev.yaml \
  up -d web script-runner
```

The override sets the compose project name (`cmdev`) and injects the cm-specific env file so this stack never reuses
the default `odoo` containers or Postgres/filestore directories.

## 5. Wire up PyCharm

1. A ready-made run configuration is checked in at `.idea/runConfigurations/Odoo_CM.run.xml`. After copying the env
   file, reload the project in PyCharm and you should see **Odoo (cm-dev)** in the run selector. It launches Odoo in
   the `cmdev-web-1` container with `-u cell_mechanic --dev=all`.
2. If you prefer to build it manually: add a **Docker Compose** configuration, include
   `docker-compose.yml`, `docker-compose.override.yml`, and `docker/config/cm-dev.yaml`; target the `script-runner`
   service; and run `/odoo/odoo-bin --dev all -d ${ODOO_DB_NAME} --config /volumes/config/_generated.conf`.
3. Optionally add a *Before launch* step that runs
   `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker/config/cm-dev.yaml up web` so PyCharm
   ensures the HTTP worker is live first.

With this configuration you can run/debug Odoo directly from PyCharm against the `cell_mechanic` database while the
default OPW stack stays untouched on ports 8069/8072.

## 6. Switch back to the default stack

Stop the cm containers when you return to the primary environment:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/cm-dev.yaml \
  down
```

Then launch your normal stack as usual (`docker compose up -d web`).
