# Architecture Overview

This page captures the current runtime topology and shows how the stack-aware deploy/restore tooling fits together. It
also highlights the remaining work for the upcoming GitHub Actions flow.

## Runtime Topology

| Environment                                         | Location                            | Compose Project | Entry Commands                                                                                                         |
|-----------------------------------------------------|-------------------------------------|-----------------|------------------------------------------------------------------------------------------------------------------------|
| Local dev (`local.odoo.outboardpartswarehouse.com`) | developer laptops                   | `odoo`          | `uv run deploy deploy --stack local --build --no-cache` (optional build); `uv run restore-from-upstream --stack local` |
| Testing (`testing.odoo.outboardpartswarehouse.com`) | `docker.shiny` (`/opt/opw-testing`) | `opw-testing`   | `uv run deploy deploy --stack opw-testing --build --no-cache`; `uv run restore-from-upstream --stack opw-testing`      |
| Dev (`dev.odoo.outboardpartswarehouse.com`)         | `docker.shiny` (`/opt/opw-dev`)     | `opw-dev`       | same commands with `opw-dev`                                                                                           |

Key points:

- Stack-specific env files live under `docker/config/<stack>.env` (not tracked); they set `ODOO_PROJECT_NAME`, database
  name, base URL, and include `DEPLOY_COMPOSE_FILES` so the stack loads `docker/config/_restore_ssh_volume.yaml` plus
  the overlay (`opw-testing.yaml`, `opw-dev.yaml`). Those overlays publish host ports (web on 18069/28069, longpoll on
  18072/28072, Postgres on 15432/25432).
- Bind mounts replace named volumes for persistent state. Set `ODOO_STATE_ROOT` per stack so the deploy tooling derives
  `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and `ODOO_LOG_DIR` (`filestore/`, `postgres/`, `logs/`; `ODOO_LOGFILE` defaults to
  `/volumes/logs/odoo.log`). When omitted, the CLI defaults to `${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`; remote stacks
  should explicitly set `/opt/odoo-ai/data/<stack>/...`.
- `docker/scripts/install_prod_requirements.sh` and `install_dev_requirements.sh` now call `uv sync` (using
  `/volumes/pyproject.toml` + `/volumes/uv.lock`), so shared Python dependencies such as `pydantic` and
  `pydantic-settings` are available in every container after a rebuild.
- `docker/config/_restore_ssh_volume.yaml` mounts the restore SSH directory. Remote stacks default to `/root/.ssh`;
  local uses `$HOME/.ssh`. In practice we generated `id_restore_opw` on `docker.shiny` and added the public key to
  `root@opw-prod.shiny`.

## Deploy & Restore Loop

1. **(Optional) Rebuild image** – `uv run deploy deploy --stack <stack> --build [--no-cache]`. The new `--build` flag
   rebuilds locally or via SSH, ensuring Python deps are synced.
2. **Restore data** – `uv run restore-from-upstream --stack <stack>`:
    - Syncs repo (detached HEAD matching the workstation commit).
    - Runs the restore script inside `script-runner` with root privileges, using the mounted key to SSH
      `root@opw-prod.shiny` for pg_dump and filestore rsync.
    - Sanitises the database (cron off, `web.base.url` freeze) and applies module updates (`ODOO_UPDATE`).
3. **Deploy/restart services** – run the deploy command again (without `--build` unless needed). Health check hits
   `/web/health` using the frozen base URL so CSS/JS load from the right hostnames.

## Application Layers

- **Base Odoo**: provided by `ghcr.io/adomi-io/odoo:18.0` (11ty-based image).
- **Custom addons**: `/volumes/addons` (repo), `/volumes/enterprise` (private mirror). Docker build stage copies both.
- **Integrations**: Shopify active. Planned flows (eBay, etc.) reuse same deploy/restore path.

## GitHub Actions (Upcoming)

- Mirror the CLI flow: checkout → `uv sync` → build (with compose overlays) → deploy.
- Restore job likely stays manual or conditional until we formalise secret handling.
- Workflow config will live under `.github/workflows/` once finalised.

## References

- Runtime commands – `docs/tooling/docker.md`
- Restore CLI – `tools/docker_runner.py`
- Deploy CLI – `tools/deployer/cli.py`
- Odoo internals – `docs/odoo/workflow.md`, `docs/odoo/orm.md`
