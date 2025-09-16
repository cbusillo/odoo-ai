#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

as_postgres() {
  if command -v runuser >/dev/null 2>&1; then
    runuser -u postgres -- "$@"
  else
    su -s /bin/sh postgres -c "$*"
  fi
}

VOLUMES_ROOT="${VOLUMES_ROOT:-/volumes}"
PGDATA_ROOT="${PGDATA_ROOT:-$VOLUMES_ROOT/data/postgres}"
PGDATA="$PGDATA_ROOT/data"
PGLOG="${PGDATA%/data}/postgres.log"
mkdir -p "$PGDATA"

ensure_role_and_db() {
  local role_name="${ODOO_DB_USER:-odoo}"
  local role_password="${ODOO_DB_PASSWORD:-odoo}"
  local db_name="${ODOO_DB_NAME:-odoo_dev}"
  local port="${POSTGRES_PORT:-5433}"

  local role_literal role_ident password_literal db_literal db_ident
  role_literal=$(sql_escape_literal "$role_name")
  role_ident=$(sql_escape_identifier "$role_name")
  password_literal=$(sql_escape_literal "$role_password")
  db_literal=$(sql_escape_literal "$db_name")
  db_ident=$(sql_escape_identifier "$db_name")

  local role_exists
  role_exists=$(as_postgres psql -p "$port" -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$role_literal'")
  if [[ -z "$role_exists" ]]; then
    as_postgres psql -p "$port" --command "CREATE ROLE \"$role_ident\" LOGIN PASSWORD '$password_literal'"
  else
    as_postgres psql -p "$port" --command "ALTER ROLE \"$role_ident\" WITH LOGIN PASSWORD '$password_literal'"
  fi

  local db_exists
  db_exists=$(as_postgres psql -p "$port" -tAc "SELECT 1 FROM pg_database WHERE datname = '$db_literal'")
  if [[ -z "$db_exists" ]]; then
    as_postgres psql -p "$port" --command "CREATE DATABASE \"$db_ident\" OWNER \"$role_ident\""
  fi
}

if command -v pg_ctlcluster >/dev/null 2>&1; then
  PG_MAJOR="${POSTGRES_VERSION:-$(psql --version 2>/dev/null | awk '{print $3}' | cut -d. -f1)}"
  if [[ -z "$PG_MAJOR" ]]; then
    log "Unable to detect PostgreSQL major version"
    exit 1
  fi

  CLUSTER_NAME="${POSTGRES_CLUSTER_NAME:-codex}"
  CLUSTER_PORT="${POSTGRES_PORT:-5433}"

  if ! pg_lsclusters | awk '{print $1" "$2}' | grep -q "^${PG_MAJOR} ${CLUSTER_NAME}$"; then
    log "Creating PostgreSQL cluster ${PG_MAJOR}/${CLUSTER_NAME}"
    pg_createcluster "$PG_MAJOR" "$CLUSTER_NAME" --datadir "$PGDATA" --port "$CLUSTER_PORT"
  else
    log "Cluster already exists; ensuring port $CLUSTER_PORT"
    pg_ctlcluster "$PG_MAJOR" "$CLUSTER_NAME" stop || true
    sed -i "s/^#\s*port = .*/port = $CLUSTER_PORT/" "$PGDATA/postgresql.conf"
  fi

  HBA_FILE="$PGDATA/pg_hba.conf"
  if ! grep -q "127.0.0.1/32" "$HBA_FILE"; then
    printf '\nhost all all 127.0.0.1/32 scram-sha-256\n' >>"$HBA_FILE"
  fi

  log "Starting PostgreSQL cluster"
  pg_ctlcluster "$PG_MAJOR" "$CLUSTER_NAME" start
  ensure_role_and_db
else
  export PGPORT="${POSTGRES_PORT:-5433}"
  log "pg_ctlcluster not available; falling back to pg_ctl"
  PG_BINDIR="${POSTGRES_BINDIR:-$(command -v pg_ctl 2>/dev/null | xargs dirname || true)}"
  if [[ -z "$PG_BINDIR" ]]; then
    log "PostgreSQL binaries not found"
    exit 1
  fi

  INITDB="$PG_BINDIR/initdb"
  PG_CTL="$PG_BINDIR/pg_ctl"

  if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    log "Initializing new PostgreSQL data directory"
    "$INITDB" -D "$PGDATA" --auth=scram-sha-256 --encoding=UTF8
    echo "listen_addresses = '127.0.0.1'" >>"$PGDATA/postgresql.conf"
    echo "port = ${POSTGRES_PORT:-5433}" >>"$PGDATA/postgresql.conf"
    cat <<HBA >>"$PGDATA/pg_hba.conf"
host all all 127.0.0.1/32 scram-sha-256
HBA
  else
    if ! grep -q "127.0.0.1/32" "$PGDATA/pg_hba.conf"; then
      printf '\nhost all all 127.0.0.1/32 scram-sha-256\n' >>"$PGDATA/pg_hba.conf"
    fi
  fi

  log "Starting PostgreSQL via pg_ctl"
  "$PG_CTL" -D "$PGDATA" -l "$PGLOG" -w start
  ensure_role_and_db
fi

log "PostgreSQL ready"
