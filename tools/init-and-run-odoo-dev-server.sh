#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

TAILSCALE_PATH="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
FLAG="${1:-}"

set +e  # Temporarily disable 'exit on error'
$TAILSCALE_PATH status > /dev/null 2>&1
INITIAL_STATE=$?
set -e  # Re-enable 'exit on error'

if ! ($TAILSCALE_PATH status > /dev/null 2>&1); then
    echo "Starting Tailscale..."
    $TAILSCALE_PATH up
else
    INITIAL_STATE=0
fi

cd ../addons/product_connect
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ -z "$CURRENT_BRANCH" ]; then
    echo "Error: Cannot find the current Git branch. Are you in a Git repository?"
    exit 1
fi

ssh "${ODOO_DEV_SERVER:-dev-server}" "bash -s" -- "$CURRENT_BRANCH" "$FLAG" << 'EOF'
FLAG=$2
CURRENT_BRANCH=$1

cd /opt/odoo/odoo-addons/product_connect
service odoo stop
echo "Current branch: $CURRENT_BRANCH"

sudo -u odoo git checkout $CURRENT_BRANCH
sudo -u odoo git pull origin $CURRENT_BRANCH

if [ "$FLAG" = "init" ]; then
    cd ..
    set -a
    source ../.env
    set +a
    ./restore_from_upstream.py
fi
EOF

echo "Starting Odoo..."
ssh "${ODOO_DEV_SERVER:-dev-server}" "service odoo start"

if [ "$INITIAL_STATE" -ne 0 ]; then
    echo "Stopping Tailscale..."
    $TAILSCALE_PATH down
fi
