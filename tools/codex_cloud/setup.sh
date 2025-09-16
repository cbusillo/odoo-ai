#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

export DEBIAN_FRONTEND=noninteractive

log "Codex Cloud setup starting"

for step in 00-system 10-python; do
  run_step "$step"
done

bash "$SCRIPT_DIR/20-database.sh"
bash "$SCRIPT_DIR/30-finalize.sh"

log "Codex Cloud setup complete"
