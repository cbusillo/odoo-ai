#!/bin/sh
set -eu

mkdir -p /enterprise /addons /addons-external

if [ -n "${ODOO_ENTERPRISE_REPOSITORY:-}" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot clone enterprise" >&2
		exit 1
	fi
	echo "Cloning Enterprise Addons from ${ODOO_ENTERPRISE_REPOSITORY} branch ${ODOO_VERSION}"
	git clone --branch "${ODOO_VERSION}" --single-branch --depth 1 \
		"https://${GITHUB_TOKEN}@github.com/${ODOO_ENTERPRISE_REPOSITORY}" /enterprise
	rm -rf /enterprise/.git
else
	echo "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone."
fi

if [ -n "${ODOO_ADDON_REPOSITORIES:-}" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot clone addons." >&2
		exit 1
	fi
	printf '%s' "${ODOO_ADDON_REPOSITORIES}" | tr ',' '\n' | while IFS= read -r raw; do
		repo="$(echo "$raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
		if [ -z "$repo" ]; then
			continue
		fi
		branch="main"
		case "$repo" in
		*@*)
			branch="${repo##*@}"
			repo="${repo%@*}"
			;;
		esac
		name="${repo##*/}"
		remote_url="https://${GITHUB_TOKEN}@github.com/${repo}"
		target_root="/addons-external"
		echo "Cloning addon from ${repo} branch ${branch} into ${target_root}/${name}"
		git clone --branch "$branch" --single-branch --depth 1 \
			"$remote_url" "${target_root}/${name}"
		rm -rf "${target_root}/${name}/.git"
	done
else
	echo "ODOO_ADDON_REPOSITORIES is empty; skipping clone."
fi
