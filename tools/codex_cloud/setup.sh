#!/usr/bin/env bash

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [[ "${TRACE-}" == "1" ]]; then
  set -x
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Codex Cloud environments run setup as root. Warn if that ever changes.
if [[ "$(id -u)" -ne 0 ]]; then
  log "Setup script expects root privileges; aborting"
  exit 1
fi

run_cmd() {
  "$@"
}

log "Installing system packages"
run_cmd apt-get update -y
run_cmd apt-get install -y git openssh-client rsync software-properties-common curl ripgrep ca-certificates

if command -v add-apt-repository >/dev/null 2>&1; then
  log "Adding chromium PPA"
  run_cmd add-apt-repository -y ppa:xtradeb/apps
  run_cmd apt-get update -y
else
  log "add-apt-repository unavailable; installing chromium from default repositories"
fi

run_cmd apt-get install -y chromium fonts-liberation libu2f-udev || {
  log "Chromium install via apt failed; attempting to install chromium-browser"
  run_cmd apt-get install -y chromium-browser || log "Chromium browser package unavailable"
}

# Basic database tooling for local Postgres usage when desired.
run_cmd apt-get install -y postgresql postgresql-client

log "Cleaning apt caches"
run_cmd apt-get clean
run_cmd rm -rf /var/lib/apt/lists/*

log "Ensuring uv is available"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"

if [[ -d "$HOME/.local/bin" ]]; then
  if [[ -w /usr/local/bin ]]; then
    for bin in "$HOME"/.local/bin/uv*; do
      [[ -f "$bin" ]] || continue
      cp "$bin" /usr/local/bin/
    done
  else
    log "Skipping /usr/local/bin uv shim (no permission)"
  fi
fi

UV_BIN="$(command -v uv)"

VOLUMES_ROOT="${VOLUMES_ROOT:-/volumes}"

log "Preparing volume directories"
if [[ ! -d "$VOLUMES_ROOT" ]]; then
  mkdir -p "$VOLUMES_ROOT"
  chown "$(id -u):$(id -g)" "$VOLUMES_ROOT"
fi

for subdir in addons config scripts enterprise data opt; do
  if [[ ! -d "$VOLUMES_ROOT/$subdir" ]]; then
    mkdir -p "$VOLUMES_ROOT/$subdir"
  fi
done

VENV_PATH="${VENV_PATH:-$VOLUMES_ROOT/.venv}"
if [[ ! -d "$VENV_PATH" ]]; then
  log "Creating virtual environment at $VENV_PATH"
  "$UV_BIN" venv "$VENV_PATH"
fi

export VIRTUAL_ENV="$VENV_PATH"
export PATH="$VIRTUAL_ENV/bin:$PATH"

log "Syncing project assets into volume tree"
rsync -a --delete "$PROJECT_ROOT/addons/" "$VOLUMES_ROOT/addons/"
if [[ -d "$PROJECT_ROOT/docker/config" ]]; then
  rsync -a --delete "$PROJECT_ROOT/docker/config/" "$VOLUMES_ROOT/config/"
fi
if [[ -d "$PROJECT_ROOT/docker/scripts" ]]; then
  rsync -a --delete "$PROJECT_ROOT/docker/scripts/" "$VOLUMES_ROOT/scripts/"
fi
if [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
  cp "$PROJECT_ROOT/pyproject.toml" "$VOLUMES_ROOT/pyproject.toml"
fi

if [[ -d "$VOLUMES_ROOT/scripts" ]]; then
  find "$VOLUMES_ROOT/scripts" -type f -name '*.sh' -exec chmod +x {} +
fi

log "Cloning Odoo Enterprise addons if configured"
ENTERPRISE_REPOSITORY="${ODOO_ENTERPRISE_REPOSITORY:-}"
ODOO_VERSION="${ODOO_VERSION:-18.0}"
ENTERPRISE_TARGET="$VOLUMES_ROOT/enterprise"

if [[ -n "$ENTERPRISE_REPOSITORY" ]]; then
  if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    log "GITHUB_TOKEN not provided; skipping enterprise clone"
  else
    REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${ENTERPRISE_REPOSITORY}"
    if [[ -d "$ENTERPRISE_TARGET/.git" ]]; then
      git -C "$ENTERPRISE_TARGET" fetch --depth 1 origin "$ODOO_VERSION"
      git -C "$ENTERPRISE_TARGET" reset --hard FETCH_HEAD
    else
      rm -rf "$ENTERPRISE_TARGET"
      git clone --branch "$ODOO_VERSION" --single-branch --depth 1 "$REMOTE_URL" "$ENTERPRISE_TARGET"
    fi
  fi
else
  log "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone"
fi

log "Preparing supplemental Python targets"
EXTRA_ROOT="$VOLUMES_ROOT/opt"
for folder in odoo-cleanup odoo-upgrade odoo-stubs; do
  mkdir -p "$EXTRA_ROOT/$folder"
done

"$UV_BIN" pip install --no-deps --target="$EXTRA_ROOT/odoo-cleanup" \
  odoo-addon-database-cleanup --extra-index-url https://wheelhouse.odoo-community.org/oca-simple/
"$UV_BIN" pip install --target="$EXTRA_ROOT/odoo-upgrade" git+https://github.com/odoo/upgrade-util
"$UV_BIN" pip install --target="$EXTRA_ROOT/odoo-stubs" git+https://github.com/odoo-ide/odoo-stubs@18.0

log "Configuring Python import paths"
PYTHON_BIN="${PYTHON_BIN:-$VIRTUAL_ENV/bin/python}"
SITE_PACKAGES="$($PYTHON_BIN -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
mkdir -p "$SITE_PACKAGES"

ODOO_SOURCE_PATH="${ODOO_SOURCE_PATH:-/odoo}"
cat <<EOF >"$SITE_PACKAGES/odoo_local.pth"
$ODOO_SOURCE_PATH
EOF

cat <<EOF >"$SITE_PACKAGES/odoo_enterprise.pth"
$VOLUMES_ROOT/enterprise
EOF

cat <<EOF >"$SITE_PACKAGES/upgrade_utils.pth"
$EXTRA_ROOT/odoo-upgrade
EOF

cat <<EOF >"$SITE_PACKAGES/database_cleanup.pth"
$EXTRA_ROOT/odoo-cleanup
EOF

cat <<EOF >"$SITE_PACKAGES/odoostubs.pth"
$EXTRA_ROOT/odoo-stubs
EOF

log "Persisting runtime environment variables"
RUNTIME_ENV="$VOLUMES_ROOT/config/runtime-env.sh"
mkdir -p "$(dirname "$RUNTIME_ENV")"
{
  echo "# Generated by tools/codex_cloud/setup.sh"
  echo "# shellcheck disable=SC2148"
  printf 'export PYTHONPATH=%q\n' "$SITE_PACKAGES:${PYTHONPATH:-}"
  printf 'export VIRTUAL_ENV=%q\n' "$VIRTUAL_ENV"
  printf 'export PATH=%q\n' "$VIRTUAL_ENV/bin:$PATH"
  for var in \
    ODOO_DB_HOST \
    ODOO_DB_PORT \
    ODOO_DB_HOST \
    ODOO_DB_PORT \
    ODOO_DB_NAME \
    ODOO_DB_USER \
    ODOO_DB_PASSWORD \
    ODOO_BASE_URL \
    ODOO_DEV_MODE \
    ODOO_UPDATE \
    ODOO_KEY \
    SHOPIFY_STORE_URL \
    SHOPIFY_STORE_URL_KEY \
    SHOPIFY_API_TOKEN \
    SHOPIFY_API_VERSION \
    SHOPIFY_WEBHOOK_KEY; do
    if [[ -n "${!var-}" ]]; then
      printf 'export %s=%q\n' "$var" "${!var}"
    fi
  done
} >"${RUNTIME_ENV}.tmp"
mv "${RUNTIME_ENV}.tmp" "$RUNTIME_ENV"
chmod 600 "$RUNTIME_ENV"

log "Installing project Python dependencies"
if [[ -x "$VOLUMES_ROOT/scripts/install_prod_requirements.sh" ]]; then
  "$VOLUMES_ROOT/scripts/install_prod_requirements.sh"
fi

if [[ "${COMPOSE_BUILD_TARGET:-development}" == "development" && -x "$VOLUMES_ROOT/scripts/install_dev_requirements.sh" ]]; then
  "$VOLUMES_ROOT/scripts/install_dev_requirements.sh"
fi

PATCH_TARGET="/odoo/odoo/addons/base/models/ir_ui_view.py"
PATCH_FILE="$PROJECT_ROOT/patches/fix_dev_mode_validation.patch"
if [[ -f "$PATCH_FILE" && -f "$PATCH_TARGET" ]]; then
  if ! grep -q "Skipping validation for unresolved stat button xmlid" "$PATCH_TARGET"; then
    log "Applying development patch"
    (cd / && patch -p0 < "$PATCH_FILE")
  else
    log "Patch already applied; skipping"
  fi
fi

HOOK_SETUP_FILE="$VOLUMES_ROOT/scripts/hook_setup"
if [[ -f "$HOOK_SETUP_FILE" ]]; then
  run_cmd cp "$HOOK_SETUP_FILE" /hook_setup
fi

log "Starting PostgreSQL cluster"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_PORT
export PGPORT="$POSTGRES_PORT"
export ODOO_DB_HOST="${ODOO_DB_HOST:-127.0.0.1}"
export ODOO_DB_PORT="$POSTGRES_PORT"
"$PROJECT_ROOT/tools/codex_cloud/start_services.sh"

log "Setup complete"
