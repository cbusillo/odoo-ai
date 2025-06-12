#!/bin/bash
set -euo pipefail

# Install system packages mirroring Dockerfile
apt-get update
apt-get install -y git openssh-client rsync software-properties-common
add-apt-repository -y ppa:xtradeb/apps
apt-get install -y --no-install-recommends chromium fonts-liberation libu2f-udev
rm -rf /var/lib/apt/lists/*

export CHROME_BIN=/usr/bin/chromium

# Ensure wheel is available for building local packages
pip install --break-system-packages wheel

# Clone enterprise addons if configured
if [[ -n "${ODOO_ENTERPRISE_REPOSITORY:-}" ]]; then
    echo "Cloning Enterprise Addons from ${ODOO_ENTERPRISE_REPOSITORY} branch ${ODOO_VERSION}"
    AUTH_PREFIX="https://"
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        AUTH_PREFIX="https://${GITHUB_TOKEN}@"
    fi
    export GIT_TERMINAL_PROMPT=0
    git clone --branch "${ODOO_VERSION}" --single-branch --depth 1 \
        "${AUTH_PREFIX}github.com/${ODOO_ENTERPRISE_REPOSITORY}" /volumes/enterprise || echo "Failed to clone enterprise repository"
else
    echo "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone."
    mkdir -p /volumes/enterprise
fi

# Python dependencies for this addon
pip install --break-system-packages -r requirements.txt
if [ -f requirements-dev.txt ]; then
    pip install --break-system-packages -r requirements-dev.txt
fi

# Additional tools from Dockerfile
pip install --break-system-packages --no-deps --target=/opt/odoo-cleanup \
    odoo-addon-database-cleanup --extra-index-url https://wheelhouse.odoo-community.org/oca-simple/
pip install --break-system-packages --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util
pip install --break-system-packages --target=/opt/odoo-stubs git+https://github.com/odoo-ide/odoo-stubs@18.0

# Install Odoo source if not present
ODOO_VERSION=${ODOO_VERSION:-18.0}
if [ ! -d /odoo ]; then
    git clone --depth 1 --branch "$ODOO_VERSION" https://github.com/odoo/odoo /odoo
fi

# Configure Python paths similar to Dockerfile
PYTHON_VERSION=${PYTHON_VERSION:-$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')}
SITE_PACKAGES=$(python3 -c 'import site, json; print(json.dumps(site.getsitepackages()))')
export SITE_PACKAGES
for SP in $(python3 - <<'PY'
import json, os
paths=json.loads(os.environ['SITE_PACKAGES'])
for p in paths:
    print(p)
PY
); do
    echo "/odoo" > "$SP/odoo_local.pth"
    echo "/volumes/enterprise" > "$SP/odoo_enterprise.pth"
    echo "/opt/odoo-upgrade" > "$SP/upgrade_utils.pth"
    echo "/opt/odoo-cleanup" > "$SP/database_cleanup.pth"
    echo "/opt/odoo-stubs" > "$SP/odoostubs.pth"
done

# Create enterprise stub package
mkdir -p /tmp/enterprise_stub/src
cat > /tmp/enterprise_stub/pyproject.toml <<'PY'
[project]
name = "odoo18-enterprise"
version = "18.0.0"
PY
echo "/volumes/enterprise" > /tmp/enterprise_stub/src/odoo_enterprise.pth
pip install --break-system-packages --no-build-isolation --no-deps /tmp/enterprise_stub
rm -rf /tmp/enterprise_stub

# Run custom requirement installation if available
if [ -f ./docker/scripts/install_addon_requirements.sh ]; then
    ./docker/scripts/install_addon_requirements.sh
fi

# Setup hook if available
HOOK_SETUP_FILE=./docker/scripts/hook_setup
if [ -f "$HOOK_SETUP_FILE" ]; then
    cp "$HOOK_SETUP_FILE" /
else
    echo "hook_setup file not found in ./docker/scripts, skipping"
fi

ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
