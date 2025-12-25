# Cell Mechanic Local Database

Use this recipe to run the `cell_mechanic` addon in isolation on your laptop
without touching the OPW stack. It sets a dedicated database, filestore, and
ports so PyCharm can attach cleanly.

## Setup

1. Create the local env file:

   ```bash
   cp docker/config/cm-local.env.example docker/config/cm-local.env
   ```

2. Update values as needed (`ODOO_DB_NAME`, `ODOO_STATE_ROOT`, `ODOO_UPDATE`).

3. Start the stack:

   ```bash
   uv run deploy deploy --stack cm-local
   ```

4. (Optional) Restore upstream data:

   ```bash
   uv run restore-from-upstream --stack cm-local
   ```

## PyCharm

- Use the shared run config `.run/CM_Local_Up.run.xml`, or create a Docker
  Compose run config that includes:
  `docker-compose.yml` and `docker-compose.override.yml`.
- Run `/odoo/odoo-bin --dev all -d ${ODOO_DB_NAME} --config /volumes/config/_generated.conf`
  in the `script-runner` service for debugging.

## Switch back to OPW

```bash
uv run deploy deploy --stack cm-local --down
```

Then start OPW again:

```bash
uv run deploy deploy --stack opw-local
```
