#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

filter_uv_sync_extras() {
  if [ ! -x "/venv/bin/python3" ]; then
    echo ""
    return
  fi
  /venv/bin/python3 - <<'PY'
import os
from pathlib import Path
import tomllib

extras_raw = os.environ.get("UV_SYNC_EXTRAS", "")
extras = [item.strip() for item in extras_raw.split(",") if item.strip()]
if not extras:
    print("")
    raise SystemExit(0)

pyproject_path = Path("/volumes/pyproject.toml")
if not pyproject_path.exists():
    print("")
    raise SystemExit(0)

data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
optional = data.get("project", {}).get("optional-dependencies", {}) or {}
available = set(optional.keys())
selected = [extra for extra in extras if extra in available]
print(",".join(selected))
PY
}

install_vendor_requirements() {
  if [ -f "/odoo/requirements.txt" ]; then
    echo "Installing Odoo requirements..."
    #    sed -i 's/libsass==0.22.0/libsass>=0.23.0/' /odoo/requirements.txt
    #    sed -i 's/greenlet==3.1.1/greenlet>=3.3.0/' /odoo/requirements.txt
    uv pip install -r "/odoo/requirements.txt"
  fi

}

install_openupgrade_requirements() {
  if [ -d "/opt/extra_addons/openupgrade_framework" ]; then
    echo "Installing OpenUpgrade requirements..."
    uv pip install "openupgradelib==3.12.0"
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
    "/odoo/addons",
    "/volumes/addons",
    "/opt/project/addons",
    "/opt/extra_addons",
    "/opt/extra_addons/odoo-enterprise-mirror",
    "/opt/extra_addons/OpenUpgrade",
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
    filtered_extras=$(filter_uv_sync_extras)
    if [ -n "$filtered_extras" ]; then
      OLD_IFS=$IFS
      IFS=','
      for extra in ${filtered_extras}; do
        trimmed=$(echo "$extra" | xargs)
        if [ -n "$trimmed" ]; then
          UV_SYNC_ARGS+=("--extra" "$trimmed")
        fi
      done
      IFS=$OLD_IFS
      UV_SYNC_LABEL+=" (extras: ${filtered_extras})"
    fi
  fi
  echo "$UV_SYNC_LABEL..."
  (cd /volumes && uv sync "${UV_SYNC_ARGS[@]}")
  write_odoo_pth
fi

if [ "${SKIP_VENDOR_INSTALL:-0}" != "1" ]; then
  install_vendor_requirements
fi
install_openupgrade_requirements

# Install addon production dependencies only
install_addon_requirements() {
  local base_dir="$1"
  if [ ! -d "$base_dir" ]; then
    return
  fi
  cd "$base_dir"
  for addon in */; do
    case "$addon" in
      OpenUpgrade/|openupgrade_framework/|openupgrade_scripts/)
        continue
        ;;
    esac
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
