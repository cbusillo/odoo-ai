#!/usr/bin/env bash
set -euo pipefail

odoo_executable="${ODOO_BIN_PATH:-/odoo/odoo-bin}"
python_executable="${ODOO_PYTHON_EXECUTABLE:-/venv/bin/python}"
debug_host="${ODOO_DEBUG_HOST:-host.docker.internal}"
debug_port="${ODOO_DEBUG_PORT:-5678}"
debug_mode="${ODOO_DEBUG_MODE:-client}"
debug_required="${ODOO_DEBUG_REQUIRED:-0}"
odoo_config_path="${ODOO_CONFIG:-/volumes/config/_generated.conf}"

odoo_arguments=(--dev=all --workers=0)
if [ -r "$odoo_config_path" ]; then
	odoo_arguments+=(-c "$odoo_config_path")
fi
odoo_data_directory="${ODOO_DATA_DIR:-/volumes/data}"
if ! mkdir -p "$odoo_data_directory" 2>/dev/null || ! [ -w "$odoo_data_directory" ]; then
	odoo_data_directory="/tmp/odoo-data"
	mkdir -p "$odoo_data_directory"
fi
odoo_arguments+=("--data-dir=${odoo_data_directory}")

if [ -n "${ODOO_DB_HOST:-}" ]; then
	odoo_arguments+=("--db_host=${ODOO_DB_HOST}")
fi
if [ -n "${ODOO_DB_PORT:-}" ]; then
	odoo_arguments+=("--db_port=${ODOO_DB_PORT}")
fi
if [ -n "${ODOO_DB_USER:-}" ]; then
	odoo_arguments+=("--db_user=${ODOO_DB_USER}")
fi
if [ -n "${ODOO_DB_PASSWORD:-}" ]; then
	odoo_arguments+=("--db_password=${ODOO_DB_PASSWORD}")
fi
if [ -n "${ODOO_DB_NAME:-}" ]; then
	odoo_arguments+=(-d "$ODOO_DB_NAME")
fi
odoo_arguments+=("$@")

if ! [ -x "$python_executable" ]; then
	python_executable="python3"
fi

if [ "$debug_mode" = "server" ]; then
	exec "$python_executable" -m pydevd --port "$debug_port" --server --multiprocess \
		--file "$odoo_executable" "${odoo_arguments[@]}"
fi

if [ "$debug_required" = "1" ]; then
	exec "$python_executable" -m pydevd --port "$debug_port" --client "$debug_host" --multiprocess \
		--file "$odoo_executable" "${odoo_arguments[@]}"
fi

if "$python_executable" - <<'PY'; then
import os
import socket
import sys

host = os.environ.get("ODOO_DEBUG_HOST", "host.docker.internal")
port = int(os.environ.get("ODOO_DEBUG_PORT", "5678"))
socket_timeout = float(os.environ.get("ODOO_DEBUG_TIMEOUT", "0.5"))

with socket.socket() as client:
    client.settimeout(socket_timeout)
    try:
        client.connect((host, port))
    except OSError:
        sys.exit(1)
sys.exit(0)
PY
	exec "$python_executable" -m pydevd --port "$debug_port" --client "$debug_host" --multiprocess \
		--file "$odoo_executable" "${odoo_arguments[@]}"
fi

echo "pydevd not reachable at ${debug_host}:${debug_port}; starting without debugger." >&2
exec "$odoo_executable" "${odoo_arguments[@]}"
