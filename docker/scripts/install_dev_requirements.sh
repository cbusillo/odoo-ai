#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

uv pip install docker

# Ensure vendor requirements run even if the environment leaks skip flags
unset SKIP_VENDOR_INSTALL

# Sync project deps (with dev extras), install vendor requirements, and install addon dependencies
UV_SYNC_EXTRAS=dev /volumes/scripts/install_prod_requirements.sh

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
