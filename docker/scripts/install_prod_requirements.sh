#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

# Install Odoo requirements if present
if [ -f "/odoo/requirements.txt" ]; then
  echo "Installing Odoo requirements..."
  uv pip install -r "/odoo/requirements.txt"
fi

# Install Enterprise requirements if present
if [ -f "/volumes/enterprise/requirements.txt" ]; then
  echo "Installing Enterprise requirements..."
  uv pip install -r "/volumes/enterprise/requirements.txt"
fi

# Install shared project dependencies declared in pyproject.toml (production extras only)
if [ -f "/volumes/pyproject.toml" ]; then
  echo "Syncing project dependencies (no dev extras)..."
  (cd /volumes && uv sync --frozen --no-dev --python /venv/bin/python3)
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
