#!/bin/bash
set -eux

export UV_PROJECT_ENVIRONMENT=/venv

uv pip install docker

# First, install all production requirements (plus tooling extras)
UV_SYNC_EXTRAS=dev SKIP_VENDOR_INSTALL=1 /volumes/scripts/install_prod_requirements.sh

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

# Reinstall vendor requirements once all custom packages are in place
INSTALL_VENDOR_ONLY=1 /volumes/scripts/install_prod_requirements.sh
