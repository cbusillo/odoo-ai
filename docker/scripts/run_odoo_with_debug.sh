#!/usr/bin/env bash
set -euo pipefail

odoo_executable="${ODOO_BIN_PATH:-/odoo/odoo-bin}"
python_executable="${ODOO_PYTHON_EXECUTABLE:-/venv/bin/python}"
debug_host="${ODOO_DEBUG_HOST:-host.docker.internal}"
debug_port="${ODOO_DEBUG_PORT:-5678}"
debug_mode="${ODOO_DEBUG_MODE:-client}"
debug_required="${ODOO_DEBUG_REQUIRED:-0}"

if ! [ -x "$python_executable" ]; then
	python_executable="python3"
fi

if [ "$debug_mode" = "server" ]; then
	exec "$python_executable" -m pydevd --port "$debug_port" --server --multiprocess \
		--file "$odoo_executable" --dev=all --workers=0 "$@"
fi

if [ "$debug_required" = "1" ]; then
	exec "$python_executable" -m pydevd --port "$debug_port" --client "$debug_host" --multiprocess \
		--file "$odoo_executable" --dev=all --workers=0 "$@"
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
		--file "$odoo_executable" --dev=all --workers=0 "$@"
fi

echo "pydevd not reachable at ${debug_host}:${debug_port}; starting without debugger." >&2
exec "$odoo_executable" --dev=all --workers=0 "$@"
