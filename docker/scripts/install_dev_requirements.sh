#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

uv pip install docker

# First, install all production requirements
/volumes/scripts/install_prod_requirements.sh

# Then install dev-specific requirements
cd /volumes/addons
for addon in */ ; do
  # Install dev requirements.txt if present
  if [ -f "${addon}requirements-dev.txt" ]; then
    echo "Installing ${addon} dev requirements..."
    uv pip install -r "${addon}requirements-dev.txt"
  fi
  
  # Install dev dependencies from pyproject.toml
  if [ -f "${addon}pyproject.toml" ]; then
    echo "Installing ${addon} dev dependencies from pyproject.toml..."
    cd "${addon}"
    uv pip install ".[dev]"
    cd ..
  fi
done

cd /volumes/addons

# Install dev extras for the shared project if defined
if [ -f "/volumes/pyproject.toml" ]; then
  cd /volumes
  uv sync --frozen --python /venv/bin/python3
fi
