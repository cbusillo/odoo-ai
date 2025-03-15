#!/bin/bash
set -euo pipefail

echo "Fetching db from production..."

BACKUP_PATH="/tmp/prod_db_backup.sql.gz"
# shellcheck disable=SC2029
ssh "$ODOO_PROD_USER"@"$ODOO_PROD_SERVER" "cd /tmp && sudo -u '$ODOO_PROD_DB_USER' pg_dump -Fc '$ODOO_PROD_DB'" | gzip > "$BACKUP_PATH"

export PGPASSWORD="$ODOO_DB_PASSWORD"
dropdb --if-exists -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" "$ODOO_DB"
createdb -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" "$ODOO_DB"

gunzip < "$BACKUP_PATH" | pg_restore -d "$ODOO_DB" -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" --no-owner --role="$ODOO_DB_USER"
echo "Database restoration from production completed."
rm "$BACKUP_PATH"