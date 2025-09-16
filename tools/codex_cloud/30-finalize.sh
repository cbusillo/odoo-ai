#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

source "$VOLUMES_ROOT/config/runtime-env.sh" 2>/dev/null || true

POSTGRES_PORT="${POSTGRES_PORT:-5433}"
POSTGRES_HOST="${ODOO_DB_HOST:-127.0.0.1}"
export PGPASSWORD="${ODOO_DB_PASSWORD:-}"

log "Running Postgres smoke check"
if ! OUTPUT=$(psql -h "$POSTGRES_HOST" \
                  -p "$POSTGRES_PORT" \
                  -U "${ODOO_DB_USER:-odoo}" \
                  -d "${ODOO_DB_NAME:-odoo_dev}" \
                  -c 'SELECT 1;' 2>&1); then
  log "Postgres smoke check failed:\n$OUTPUT"
  exit 1
fi

log "Python environment check"
uv run --version >/dev/null 2>&1

if [[ -f /var/log/postgresql/postgresql-16-codex.log ]]; then
  log "Postgres recent log tail"
  tail -n 20 /var/log/postgresql/postgresql-16-codex.log || true
fi
