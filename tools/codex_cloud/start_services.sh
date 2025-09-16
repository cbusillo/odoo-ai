#!/usr/bin/env bash

set -euo pipefail

if [[ "${TRACE-}" == "1" ]]; then
  set -x
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

if [[ -z "$SUDO" && "$(id -u)" -ne 0 ]]; then
  log "sudo is required to manage PostgreSQL services"
  exit 1
fi

VOLUMES_ROOT="${VOLUMES_ROOT:-/volumes}"
PGDATA="${PGDATA:-$VOLUMES_ROOT/data/postgres}"/data
PGLOG="${PGDATA%/data}/postgres.log"
mkdir -p "$PGDATA"

ensure_role_and_db() {
  local role_name="${ODOO_DB_USER:-odoo}"
  local role_password="${ODOO_DB_PASSWORD:-odoo}"
  local db_name="${ODOO_DB_NAME:-odoo_dev}"

  ${SUDO:+$SUDO }-u postgres psql <<SQL
DO
$$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$role_name') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '$role_name', '$role_password');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '$role_name', '$role_password');
  END IF;
END
$$;
SQL

  ${SUDO:+$SUDO }-u postgres psql <<SQL
DO
$$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$db_name') THEN
    EXECUTE format('CREATE DATABASE %I OWNER %I', '$db_name', '$role_name');
  END IF;
END
$$;
SQL
}

if command -v pg_ctlcluster >/dev/null 2>&1; then
  PG_MAJOR="${POSTGRES_VERSION:-$(psql --version 2>/dev/null | awk '{print $3}' | cut -d. -f1)}"
  if [[ -z "$PG_MAJOR" ]]; then
    log "Unable to detect PostgreSQL major version"
    exit 1
  fi

  CLUSTER_NAME="${POSTGRES_CLUSTER_NAME:-codex}"

  if ! ${SUDO:+$SUDO }pg_lsclusters | awk '{print $1" "$2}' | grep -q "^${PG_MAJOR} ${CLUSTER_NAME}$"; then
    log "Creating PostgreSQL cluster ${PG_MAJOR}/${CLUSTER_NAME}"
    ${SUDO:+$SUDO }pg_createcluster "$PG_MAJOR" "$CLUSTER_NAME" --datadir "$PGDATA"
  fi

  log "Starting PostgreSQL cluster"
  ${SUDO:+$SUDO }pg_ctlcluster "$PG_MAJOR" "$CLUSTER_NAME" start
  ensure_role_and_db
else
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
    cat <<HBA >>"$PGDATA/pg_hba.conf"
host all all 127.0.0.1/32 scram-sha-256
HBA
  fi

  log "Starting PostgreSQL via pg_ctl"
  "$PG_CTL" -D "$PGDATA" -l "$PGLOG" -w start
  ensure_role_and_db
fi

log "PostgreSQL ready"
