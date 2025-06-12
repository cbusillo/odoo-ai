#!/bin/bash
set -euo pipefail

apt-get update
apt-get install -y git openssh-client rsync software-properties-common
add-apt-repository -y ppa:xtradeb/apps
apt-get install -y --no-install-recommends chromium fonts-liberation libu2f-udev build-essential libldap2-dev libsasl2-dev libssl-dev
rm -rf /var/lib/apt/lists/*

git config submodule.addons/product_connect.url \
    "https://${GITHUB_TOKEN}@github.com/cbusillo/product_connect.git"
git config submodule.addons/disable_odoo_online.url \
    "https://${GITHUB_TOKEN}@github.com/cbusillo/disable_odoo_online.git"

git submodule update --init --recursive

export CHROME_BIN=/usr/bin/chromium

pip install --break-system-packages wheel

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

pip install --break-system-packages --no-deps --target=/opt/odoo-cleanup \
    odoo-addon-database-cleanup --extra-index-url https://wheelhouse.odoo-community.org/oca-simple/
pip install --break-system-packages --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util
pip install --break-system-packages --target=/opt/odoo-stubs git+https://github.com/odoo-ide/odoo-stubs@18.0

ODOO_VERSION=${ODOO_VERSION:-18.0}
if [ ! -d /odoo ]; then
    git clone --depth 1 --branch "${ODOO_VERSION}" https://github.com/odoo/odoo /odoo
fi

pip install --break-system-packages -r /odoo/requirements.txt
if [ -f /odoo/requirements-dev.txt ]; then
    pip install --break-system-packages -r /odoo/requirements-dev.txt
fi

PYTHON_VERSION=${PYTHON_VERSION:-$(python3 - <<'PY'
import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)}
SITE_PACKAGES=$(python3 - <<'PY'
import site, json, sys; print(json.dumps(site.getsitepackages()))
PY
)
export SITE_PACKAGES
for PACKAGE_PATH in $(python3 - <<'PY'
import json, os; print("\n".join(json.loads(os.environ["SITE_PACKAGES"])))
PY
); do
    echo "/odoo" > "${PACKAGE_PATH}/odoo_local.pth"
    echo "/volumes/enterprise" > "${PACKAGE_PATH}/odoo_enterprise.pth"
    echo "/opt/odoo-upgrade" > "${PACKAGE_PATH}/upgrade_utils.pth"
    echo "/opt/odoo-cleanup" > "${PACKAGE_PATH}/database_cleanup.pth"
    echo "/opt/odoo-stubs" > "${PACKAGE_PATH}/odoostubs.pth"
done

mkdir -p /tmp/enterprise_stub/src
cat > /tmp/enterprise_stub/pyproject.toml <<'PY'
[project]
name = "odoo18-enterprise"
version = "18.0.0"
PY
echo "/volumes/enterprise" > /tmp/enterprise_stub/src/odoo_enterprise.pth
pip install --break-system-packages --no-build-isolation --no-deps /tmp/enterprise_stub
rm -rf /tmp/enterprise_stub

mkdir -p /volumes/config /volumes/scripts /volumes/addons
cp -r docker/config/. /volumes/config 2>/dev/null || true
cp -r docker/scripts/. /volumes/scripts 2>/dev/null || true
rsync -a addons/ /volumes/addons/ 2>/dev/null || true

cd /volumes/addons
if [ -x /volumes/scripts/install_addon_requirements.sh ]; then
    /volumes/scripts/install_addon_requirements.sh
fi

export HOOK_SETUP_FILE=/volumes/scripts/hook_setup
if [ -f "${HOOK_SETUP_FILE}" ]; then
    cp "${HOOK_SETUP_FILE}" /
else
    echo "hook_setup file not found in /volumes/scripts, skipping"
fi

ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt