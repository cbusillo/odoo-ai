#!/usr/bin/env bash

set -euo pipefail

if [[ "${TRACE-}" == "1" ]]; then
  set -x
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

ensure_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    log "This script must run as root"
    exit 1
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VOLUMES_ROOT="${VOLUMES_ROOT:-/volumes}"
CACHE_DIR="${CACHE_DIR:-$VOLUMES_ROOT/cache/setup}"
MARKER_DIR="$CACHE_DIR/markers"

mkdir -p "$CACHE_DIR" "$MARKER_DIR"

run_step() {
  local step="$1"
  local script="$SCRIPT_DIR/${step}.sh"
  local marker="$MARKER_DIR/${step}.done"

  if [[ ! -f "$script" ]]; then
    log "Step script $script not found"
    exit 1
  fi

  if [[ -n "${FORCE_SETUP:-}" ]]; then
    rm -f "$marker"
  fi

  if [[ -f "$marker" ]]; then
    log "Skipping step $step (cached)"
    return 0
  fi

  log "Running step $step"
  bash "$script"
  touch "$marker"
  log "Completed step $step"
}

ensure_dir() {
  local path="$1"
  mkdir -p "$path"
}

sql_escape_literal() {
  printf '%s' "$1" | sed "s/'/''/g"
}

sql_escape_identifier() {
  printf '%s' "$1" | sed 's/"/""/g'
}
