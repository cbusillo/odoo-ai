Title: Codex CLI

Purpose

- Run Codex sessions with explicit sandbox/approval and small, focused context.

Profiles (local ~/.codex/config.toml)

- quick (read-only)
- dev-standard (workspace-write, approval on-failure)
- deep-reasoning (like dev-standard, more reasoning time)
- inspector (read-only)
- test-runner (workspace-write)

Notes

- Omit model unless you must override the CLI default.
- Set `sandbox` explicitly per run; prefer `workspace-write` for implementation, `read-only` for analysis.

Codex Cloud Environment

- Setup Script: Point the environment Setup Script to `tools/codex_cloud/setup.sh`. It mirrors `docker/Dockerfile` by
  installing apt packages (Chromium, ripgrep, Postgres), bootstrapping `uv`, syncing `/volumes/*`, and installing
  addon requirements.
- Maintenance Script: Point the environment Maintenance Script to `tools/codex_cloud/start_services.sh` to
  restart the local Postgres cluster on demand. The setup script already runs it once during every cold boot, so the
  maintenance hook is only needed if you have to reset the database mid-session.
- Runtime Launch: The environment is non-interactive; agent commands run after setup completes. Use
  `uv run odoo-bin --dev all -d $ODOO_DB_NAME` (or test commands) from tasks as needed—Postgres is already active once
  setup finishes.
- Required Secrets (Codex secrets are injected only during the Setup Script and removed before tasks
  executeciteturn1search0):
    - `GITHUB_TOKEN` — used while cloning the Enterprise repo in setup.
    - Optional Shopify credentials (`SHOPIFY_*`) or upstream sync keys that should never appear as plain env vars. Have
      the setup script persist them to `/volumes/config/runtime-env.sh` with `chmod 600` if they must be available
      later.
- Runtime Environment Variables (added via the Codex UI so they persist for agent commands):
    - `ODOO_DB_USER`, `ODOO_DB_PASSWORD`, `ODOO_DB_NAME`, `ODOO_DB_HOST`, `ODOO_DB_PORT` (defaults in `.env.example`).
    - `ODOO_ENTERPRISE_REPOSITORY`, `ODOO_VERSION`, `PYTHON_VERSION`, `COMPOSE_BUILD_TARGET`, and any feature flags.
- Runtime Shell Setup: The setup script writes `/volumes/config/runtime-env.sh` with the exported variables above; have
  tasks source it (e.g., `source /volumes/config/runtime-env.sh`) before running Odoo or tests so credentials survive
  the setup-only secret window.citeturn1search0
- Virtualenv: Setup creates `/volumes/.venv` with `uv venv`, writes `.pth` files into that environment’s site-packages,
  exports `VIRTUAL_ENV`, and prepends it to `PATH`, keeping every subsequent `uv pip` call inside the same environment.
- Database Host/Port: Postgres is launched on `127.0.0.1:$POSTGRES_PORT` (default 5433); the setup script exports
  those variables and persists them to the runtime env file so Odoo connects to the right socket.
- Environment Variables (non-secret): `ODOO_ENTERPRISE_REPOSITORY`, `ODOO_VERSION`, `PYTHON_VERSION`, and any
  integration feature flags that need to be ready before setup executes.
- Internet Access: Request allowlist entries for `github.com`, `pypi.org`, `files.pythonhosted.org`, `astral.sh`,
  `wheelhouse.odoo-community.org`, and any managed Postgres host. Allow methods `GET`, `HEAD`, `OPTIONS` unless an
  integration requires broader verbs.
- Maintenance Runs: Re-trigger the environment when requirements change; cache hits reuse the previous virtualenv, so
  bumping dependencies requires rerunning `tools/codex_cloud/setup.sh` via the Codex UI.
