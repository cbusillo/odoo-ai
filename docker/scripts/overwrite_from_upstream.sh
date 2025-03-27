#!/bin/bash
set -euo pipefail
#set -x

echo "Overwriting filestore from production..."
rsync -az --delete "$ODOO_UPSTREAM_USER@$ODOO_UPSTREAM_SERVER:$ODOO_UPSTREAM_FILESTORE_PATH" /volumes/data &
FILESTORE_RSYNC_PID=$!

echo "Overwriting database from upstream..."
if /volumes/scripts/overwrite_from_upstream_db.sh; then
    echo "Database overwritten, now sanitizing..."
    if ! odoo shell --no-http --stop-after-init -d "$ODOO_DB" < /volumes/scripts/sanitize_db.py; then
        echo "Database sanitization FAILED. Deleting database for safety."
        export PGPASSWORD="$ODOO_DB_PASSWORD"
        dropdb -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" "$ODOO_DB"
        exit 1
    fi
else
    echo "Database overwrite FAILED. Exiting immediately."
    exit 1
fi

wait $FILESTORE_RSYNC_PID
echo "Filestore rsync from upstream completed."

echo "Updating Odoo addons..."
ADDONS_FOLDER="/volumes/addons"
ADDON_LIST=$(find "$ADDONS_FOLDER" -maxdepth 1 -type d -not -path "$ADDONS_FOLDER" -exec basename {} \; | tr '\n' ',' | sed 's/,$//')
odoo --stop-after-init -d "$ODOO_DB" --no-http -u "$ADDON_LIST"
echo "$ADDON_LIST Odoo addons updated."