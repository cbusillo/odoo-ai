Title: Cell Mechanic Local Database

Use this recipe when you want to work on the `cell_mechanic` addon in isolation without disturbing the default OPW
stack. It defines a dedicated database, filestore, and port mappings and integrates cleanly with PyCharm's Docker
compose run configurations.

## 1. Prepare environment overrides

1. Create `docker/config/cm-local.env` with your stack-specific configuration.
2. Adjust values as needed:
    - `COMPOSE_PROJECT_NAME` controls the Docker project slug; use `cm-local` so container names are
      `cm-local-web-1`, `cm-local-database-1`, etc.
    - `ODOO_DB_NAME` & `ODOO_PROJECT_NAME` control the database name and Odoo config label inside the container.
    - `ODOO_UPDATE` defaults to `cell_mechanic`; add additional module names if you want them auto-installed.
    - Port variables are already offset from the main stack (`9069/9072/9432` via the `cm-local.yaml` overlay). Change
      them if those ports are occupied locally.

## 2. One-click init via run configs

Shared PyCharm run configurations live in the tracked `.idea/runConfigurations/` directory:

- `OPW Local Init` (`.idea/runConfigurations/OPW_Local_Init.run.xml`) bootstraps the OPW stack with
  `uv run restore-from-upstream --stack opw-local --bootstrap-only`.
- `CM Local Init` (`.idea/runConfigurations/CM_Local_Init.run.xml`) performs the same bootstrap for the CM stack so you
  start from a clean database and filestore.
- `OPW Local Up` / `CM Local Up` (`.idea/runConfigurations/OPW_Local_Up.run.xml`,
  `.idea/runConfigurations/CM_Local_Up.run.xml`) bring the corresponding stacks online after configuration changes.
- `OPW Local Restore` / `CM Local Restore` (`.idea/runConfigurations/OPW_Local_Restore.run.xml`,
  `.idea/runConfigurations/CM_Local_Restore.run.xml`) refresh local data from upstream.
- `OPW Testing Restore` (`.idea/runConfigurations/OPW_Testing_Restore.run.xml`) runs the upstream restore for the
  remote testing stack.

Bootstrap mode clears any existing database, installs modules from `ODOO_UPDATE`, and hardens the admin password if
`ODOO_ADMIN_PASSWORD` is set.

## 3. Restore the cm database (optional)

If you need a fresh snapshot from upstream, run the restore helper:

```bash
uv run restore-from-upstream --stack cm-local
```

The script will create the database, sync the filestore under `${ODOO_STATE_ROOT}`, and apply `ODOO_UPDATE` modules.

## 4. Start the Docker services

The layered compose configuration follows the pattern `base.yaml` → `project.yaml` (e.g., `cm-local.yaml`):

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/cm-local.yaml \
  up -d web script-runner
```

Or use the deploy tooling which reads `DEPLOY_COMPOSE_FILES` from your stack's `.env`:

```bash
uv run deploy deploy --stack cm-local
```

The `cm-local.yaml` overlay sets the compose project name (`cm-local`) and injects the cm-specific env file so this
stack never reuses the default `odoo` containers or Postgres/filestore directories.

## 5. Wire up PyCharm

1. The shared `.idea/runConfigurations/CM_Local_Up.run.xml` run configuration brings the Docker stack online. After the
   running you can add a standard **Docker Compose** or **Python** configuration for interactive debugging if needed.
2. If you prefer to build it manually: add a **Docker Compose** configuration, include
   `docker-compose.yml`, `docker-compose.override.yml`, and `docker/config/cm-local.yaml`; target the `script-runner`
   service; and run `/odoo/odoo-bin --dev all -d ${ODOO_DB_NAME} --config /volumes/config/_generated.conf`.
3. Optionally add a *Before launch* step that runs
   `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker/config/cm-local.yaml up web` so
   PyCharm ensures the HTTP worker is live first.

With this configuration you can run/debug Odoo directly from PyCharm against the `cell_mechanic` database while the
default OPW stack stays untouched on ports 8069/8072.

## 6. Switch back to the default stack

Stop the cm containers when you return to the primary environment:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/cm-local.yaml \
  down
```

Or use the deploy tooling:

```bash
uv run deploy deploy --stack cm-local --down
```

Then launch your normal stack as usual (`uv run deploy deploy --stack opw-local` or `docker compose up -d web`).
