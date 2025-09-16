#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_PORT
export PGPORT="$POSTGRES_PORT"
export ODOO_DB_HOST="127.0.0.1"
export ODOO_DB_PORT="$POSTGRES_PORT"
export ODOO_DB_USER="${ODOO_DB_USER:-odoo}"
export ODOO_DB_PASSWORD="${ODOO_DB_PASSWORD:-odoo}"
export ODOO_DB_NAME="${ODOO_DB_NAME:-odoo_dev}"

RUNTIME_ENV="$VOLUMES_ROOT/config/runtime-env.sh"
if [[ -f "$RUNTIME_ENV" ]]; then
  tmp_file="$(mktemp)"
  grep -vE '^export ODOO_DB_(HOST|PORT|USER|PASSWORD|NAME)=' "$RUNTIME_ENV" >"$tmp_file" || true
  {
    printf 'export ODOO_DB_HOST=%q\n' "$ODOO_DB_HOST"
    printf 'export ODOO_DB_PORT=%q\n' "$ODOO_DB_PORT"
    printf 'export ODOO_DB_USER=%q\n' "$ODOO_DB_USER"
    printf 'export ODOO_DB_PASSWORD=%q\n' "$ODOO_DB_PASSWORD"
    printf 'export ODOO_DB_NAME=%q\n' "$ODOO_DB_NAME"
  } >>"$tmp_file"
  mv "$tmp_file" "$RUNTIME_ENV"
  chmod 600 "$RUNTIME_ENV"
fi

"$SCRIPT_DIR/start_services.sh"
