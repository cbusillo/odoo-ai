#!/bin/bash
set -euo pipefail

BACKUP_PATH="/tmp/upstream_db_backup.sql.gz"
# shellcheck disable=SC2029
ssh "$ODOO_UPSTREAM_USER"@"$ODOO_UPSTREAM_SERVER" "cd /tmp && sudo -u '$ODOO_UPSTREAM_DB_USER' pg_dump -Fc '$ODOO_UPSTREAM_DB'" | gzip > "$BACKUP_PATH"

export PGPASSWORD="$ODOO_DB_PASSWORD"
dropdb --if-exists -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" "$ODOO_DB"
createdb -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" "$ODOO_DB"

gunzip < "$BACKUP_PATH" | pg_restore -d "$ODOO_DB" -h "$ODOO_DB_HOST" -U "$ODOO_DB_USER" --no-owner --role="$ODOO_DB_USER"

rm "$BACKUP_PATH"