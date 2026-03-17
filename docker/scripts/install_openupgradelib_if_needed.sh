#!/usr/bin/env bash

set -euo pipefail

openupgrade_addon_repository="${OPENUPGRADE_ADDON_REPOSITORY:-}"
addon_repositories="${ODOO_ADDON_REPOSITORIES:-}"
install_specification="${OPENUPGRADELIB_INSTALL_SPEC:-}"

if [[ -z "${openupgrade_addon_repository}" ]]; then
	exit 0
fi

if [[ ",${addon_repositories}," != *",${openupgrade_addon_repository},"* ]]; then
	exit 0
fi

if [[ -z "${install_specification}" ]]; then
	echo "OPENUPGRADELIB_INSTALL_SPEC is required when OpenUpgrade addons are enabled" >&2
	exit 1
fi

uv pip install --python /venv/bin/python "${install_specification}"
