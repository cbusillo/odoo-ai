#!/bin/bash
set -euo pipefail
#set -x

echo "Fetching filestore from production..."
rsync -az --delete "$ODOO_PROD_USER@$ODOO_PROD_SERVER:$ODOO_PROD_FILESTORE_PATH" /volumes/data
echo "Filestore sync from production completed."