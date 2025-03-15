#!/bin/bash
set -euo pipefail

if [[ "${FETCH_FROM_PROD:-false}" == "true" ]]; then
  /volumes/scripts/pull_db_from_prod.sh &
  DB_PULL_PID=$!

  /volumes/scripts/pull_filestore_from_prod.sh &
  FILESTORE_PULL_PID=$!

  wait $DB_PULL_PID

  if ! odoo shell --no-http --stop-after-init -d "$ODOO_DB" < /volumes/scripts/sanitize_db.py; then
    echo "Failed to sanitize database. Exiting..."
    exit 1
  fi

  wait $FILESTORE_PULL_PID

fi

echo "Updating Odoo addons..."
odoo --stop-after-init -d "$ODOO_DB" --no-http -u "product_connect"
echo "Odoo addons updated."