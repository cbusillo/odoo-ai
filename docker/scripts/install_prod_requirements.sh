#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

install_vendor_requirements() {
  if [ -f "/odoo/requirements.txt" ]; then
    echo "Installing Odoo requirements..."
    uv pip install -r "/odoo/requirements.txt"
  fi

  if [ -f "/volumes/enterprise/requirements.txt" ]; then
    echo "Installing Enterprise requirements..."
    uv pip install -r "/volumes/enterprise/requirements.txt"
  fi
}

# Allow callers to only refresh vendor requirements when needed (e.g. dev script)
if [ "${INSTALL_VENDOR_ONLY:-0}" = "1" ]; then
  install_vendor_requirements
  exit 0
fi

# Install shared project dependencies declared in pyproject.toml (production extras only)
if [ -f "/volumes/pyproject.toml" ]; then
  UV_SYNC_ARGS=("--frozen" "--python" "/venv/bin/python3")
  UV_SYNC_LABEL="Syncing project dependencies"
  if [ -n "${UV_SYNC_EXTRAS:-}" ]; then
    OLD_IFS=$IFS
    IFS=','
    for extra in ${UV_SYNC_EXTRAS}; do
      trimmed=$(echo "$extra" | xargs)
      if [ -n "$trimmed" ]; then
        UV_SYNC_ARGS+=("--extra" "$trimmed")
      fi
    done
    IFS=$OLD_IFS
    UV_SYNC_LABEL+=" (extras: ${UV_SYNC_EXTRAS})"
  fi
  echo "$UV_SYNC_LABEL..."
  (cd /volumes && uv sync "${UV_SYNC_ARGS[@]}")
fi

# Install addon production dependencies only
cd /volumes/addons
for addon in */ ; do
  if [ -f "${addon}requirements.txt" ]; then
    echo "Installing ${addon} production requirements..."
    uv pip install -r "${addon}requirements.txt"
  fi

  if [ -f "${addon}pyproject.toml" ]; then
    echo "Installing ${addon} production dependencies from pyproject.toml..."
    cd "${addon}"
    # Install without editable mode and without dev dependencies
    uv pip install .
    cd ..
  fi
done

cd /volumes/addons

if [ "${SKIP_VENDOR_INSTALL:-0}" != "1" ]; then
  install_vendor_requirements
fi
