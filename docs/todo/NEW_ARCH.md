# Dev & Testing Container Architecture — Clean Sheet

This document replaces prior webhook/worker automation plans. It describes the
lean deployment model for Odoo 18 Enterprise dev and testing environments on
`docker.shiny` using GitHub Actions, private container images, and Docker
Compose overlays.

---

## Objectives

- Keep the `odoo-ai` repository environment-agnostic; no secrets or host paths
  committed.
- Use a single automation surface: GitHub Actions builds + deploys per branch.
- Ensure Odoo Enterprise sources and API keys never land in git or public
  artifacts.
- Minimise moving parts on `docker.shiny`: only Docker + Compose.
- Provide fast rollback via tagged images and compose overrides.

---

## Branch & Environment Map

- `main` → Dev stack (`opw-dev`).
- `testing` → Testing stack (`opw-testing`).
- `prod` (future) → Production stack when promoted.

Every successful build produces a container tag `<env>-<short-sha>` stored in a
private registry (recommended: GHCR). Rollback equals re-running the deploy job
with a previous tag.

---

## Repository Layout

- `docker-compose.yml`: baseline services (web, script-runner, database,
  optional cache/proxy).
- `environments/dev.yaml`, `environments/testing.yaml`: environment overlays
  that set ports, volumes, and module lists.
- `.github/workflows/deploy.yml`: GitHub Actions pipeline (see below).
- Addons live as submodules or separate repos pulled during build.

No `.env` files are committed; they are generated from secrets during deploy.

---

## docker.shiny Layout

```
/opt/odoo-ai/
├── repos/
│   ├── opw-dev/                # git clone synced to the requested commit
│   └── opw-testing/
├── data/
│   ├── opw-dev/
│   │   ├── .env                # rendered from secrets (chmod 600)
│   │   ├── filestore/
│   │   ├── postgres/
│   │   ├── logs/
│   │   └── cache/
│   └── opw-testing/...
├── environments/
│   ├── dev.yaml
│   └── testing.yaml
└── releases.log                # append-only deploy history (optional)
```

Each stack’s env lives in `docker/config/<env>.env` (kept out of version control) and should set
`ODOO_STATE_ROOT=/opt/odoo-ai/data/<env>` so the deploy tooling expands it to `ODOO_DATA_DIR`, `ODOO_DB_DIR`, and
`ODOO_LOG_DIR` (`filestore/`, `postgres/`, `logs/`). `ODOO_LOGFILE` should point to `/volumes/logs/odoo.log` (or another
filename under that directory). If `ODOO_STATE_ROOT` is omitted (local dev), the CLI defaults to
`${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`; remote stacks should always set explicit `/opt/odoo-ai/data/<env>/...`
paths.

The host may keep a read-only clone of the repo for reference, but automation
does not rely on it. Ingress can continue to flow through Nginx Proxy Manager
with simple port mappings mirroring the compose overrides.

---

## Secrets & Enterprise Handling

- GitHub Actions **environment secrets** per stage store:
    - `ODOO_ENTERPRISE_SSH_KEY` (or a signed URL for tarball download).
    - Runtime values (`ODOO_MASTER_PASSWORD`, `SHOPIFY_API_TOKEN`, DB creds,
      etc.).
    - `DOCKER_SHINY_SSH_KEY` (deploy key).
- Build uses Docker BuildKit secrets (`--secret id=enterprise_key,...`) so
  credentials never end up in image layers.
- Deploy job renders `/opt/odoo-ai/opw-<env>/.env` from secrets just
  before `docker compose up`; permissions locked to `600`.
- Secrets are not persisted elsewhere; GitHub workflow deletes temporary files
  post-deploy.

---

## GitHub Actions Workflow

Triggers: push to `main`, `testing` (and manual `workflow_dispatch` for
rollback/promotion).

### `build` job (runs on self-hosted runner with Docker access)

1. Checkout repo.
2. Fetch Odoo Enterprise using `ODOO_ENTERPRISE_SSH_KEY`.
3. Run fast tests (`uv run test run --json` or targeted shards).
4. Build multi-stage images (`web`, `script-runner`) tagged `ghcr.io/<org>/odoo:<env>-<sha>`.
5. Push tags to the private registry and expose the image digest as a job
   output.

### `deploy_<env>` job (one per environment)

1. Needs `build`; runs on the same self-hosted runner.
2. SSH into `docker.shiny` using deploy key.
3. Write `.env` from secrets into `/opt/odoo-ai/data/opw-<env>/.env`.
4. `IMAGE_TAG=<digest> docker compose -f docker-compose.yml -f environments/<env>.yaml pull web script-runner`.
5. `docker compose ... up -d --remove-orphans`.
6. `docker compose exec script-runner /odoo/odoo-bin -u $ODOO_UPDATE -d $ODOO_DB_NAME --stop-after-init`.
7. Health check: `curl -sf http://localhost:<port>/web/health` (add simple
   controller returning 200). Failures abort the job and leave the previous
   containers running.
8. Append `{timestamp, env, image_tag, commit}` to `releases.log`.

Manual reruns or `workflow_dispatch` with a specific tag enable rollbacks.

---

## Rollback & Observability

- To roll back manually:
  ```bash
  IMAGE_TAG=<previous-tag> docker compose -f docker-compose.yml -f environments/dev.yaml up -d web script-runner
  docker compose exec script-runner /odoo/odoo-bin -u $ODOO_UPDATE -d $ODOO_DB_NAME --stop-after-init
  ```
- Keep the last N images in the registry; prune older ones periodically with a
  scheduled workflow.
- Health endpoint doubles as uptime probe; integrate with your monitoring stack
  (optional) by curling it from an external checker.

---

## Next Actions

1. Provision a self-hosted GitHub runner on `docker.shiny` (Docker access).
2. Stand up private registry credentials (GHCR recommended).
3. Move existing `.env` contents and SSH keys into GitHub environment secrets.
4. Author `.github/workflows/deploy.yml` implementing the jobs above.
5. Implement `/web/health` endpoint in Odoo for 200 OK health checks.
6. Update Nginx Proxy Manager to route new ports (if applicable).

This plan keeps the deployment loop simple, auditable, and free of bespoke
runtime daemons while respecting the licensing and security requirements of
Odoo Enterprise.
