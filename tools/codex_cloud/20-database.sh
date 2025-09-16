#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_PORT
export PGPORT="$POSTGRES_PORT"
export ODOO_DB_HOST="${ODOO_DB_HOST:-127.0.0.1}"
export ODOO_DB_PORT="$POSTGRES_PORT"

"$SCRIPT_DIR/start_services.sh"
