#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

install_vendor_requirements() {
  if [ -f "/odoo/requirements.txt" ]; then
    echo "Installing Odoo requirements..."
    uv pip install -r "/odoo/requirements.txt"
  fi

}

write_odoo_pth() {
  if [ ! -x "/venv/bin/python3" ]; then
    echo "Skipping .pth install; /venv/bin/python3 missing."
    return
  fi

  /venv/bin/python3 - <<'PY'
from pathlib import Path
import site

paths = [
    "/odoo",
    "/volumes/addons",
    "/opt/extra_addons",
    "/opt/odoo-upgrade",
    "/opt/odoo-stubs",
]

site_packages = Path(site.getsitepackages()[0])
pth_path = site_packages / "odoo_paths.pth"
pth_path.write_text("\n".join(paths) + "\n")
print(f"Updated {pth_path}")
PY
}

# Allow callers to only refresh vendor requirements when needed (e.g. dev script)
if [ "${INSTALL_VENDOR_ONLY:-0}" = "1" ]; then
  install_vendor_requirements
  exit 0
fi

# Install shared project dependencies declared in pyproject.toml (production extras only)
if [ -f "/volumes/pyproject.toml" ]; then
  UV_SYNC_ARGS=("--frozen")
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
  write_odoo_pth
fi

if [ "${SKIP_VENDOR_INSTALL:-0}" != "1" ]; then
  install_vendor_requirements
fi

# Install addon production dependencies only
install_addon_requirements() {
  local base_dir="$1"
  if [ ! -d "$base_dir" ]; then
    return
  fi
  cd "$base_dir"
  for addon in */; do
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
}

install_addon_requirements /volumes/addons
install_addon_requirements /opt/extra_addons

cd /volumes/addons
