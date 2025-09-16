#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

source "$VOLUMES_ROOT/config/runtime-env.sh" 2>/dev/null || true

POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export PGPASSWORD="${ODOO_DB_PASSWORD:-}"

log "Running Postgres smoke check"
psql -p "$POSTGRES_PORT" -U postgres -d postgres -c '\conninfo' 2>&1 | tail -n +1 || {
  log "Postgres smoke check failed"
  exit 1
}

log "Python environment check"
uv run --version >/dev/null 2>&1

if [[ -f /var/log/postgresql/postgresql-16-codex.log ]]; then
  log "Postgres recent log tail"
  tail -n 20 /var/log/postgresql/postgresql-16-codex.log || true
fi
