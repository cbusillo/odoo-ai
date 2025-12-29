#!/bin/sh
set -eu

log() {
	printf '%s\n' "$*"
}

mkdir -p /enterprise /addons /extra_addons

if [ -n "${ODOO_ENTERPRISE_REPOSITORY:-}" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot clone enterprise" >&2
		exit 1
	fi
	log "Cloning Enterprise Addons from ${ODOO_ENTERPRISE_REPOSITORY} branch ${ODOO_VERSION}"
	if ! git clone --branch "${ODOO_VERSION}" --single-branch --depth 1 \
		"https://${GITHUB_TOKEN}@github.com/${ODOO_ENTERPRISE_REPOSITORY}" /enterprise; then
		echo "Failed to clone enterprise repo ${ODOO_ENTERPRISE_REPOSITORY}." >&2
		exit 1
	fi
	rm -rf /enterprise/.git
else
	log "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone."
fi

if [ -n "${ODOO_ADDON_REPOSITORIES:-}" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot clone addons." >&2
		exit 1
	fi
	log "Cloning addon repositories: ${ODOO_ADDON_REPOSITORIES}"
	old_ifs="$IFS"
	IFS=','
	for raw in ${ODOO_ADDON_REPOSITORIES}; do
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
		target_root="/extra_addons"
		log "Cloning addon from ${repo} branch ${branch} into ${target_root}/${name}"
		if ! git clone --branch "$branch" --single-branch --depth 1 \
			"$remote_url" "${target_root}/${name}"; then
			echo "Failed to clone addon repo ${repo} (branch ${branch})." >&2
			exit 1
		fi
		rm -rf "${target_root}/${name}/.git"
	done
	IFS="$old_ifs"
else
	log "ODOO_ADDON_REPOSITORIES is empty; skipping clone."
fi
