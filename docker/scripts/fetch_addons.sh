#!/bin/sh
set -eu

log() {
	printf '%s\n' "$*"
}

mkdir -p /addons /extra_addons

addons_repos_raw="${ODOO_ADDON_REPOSITORIES:-}"
addons_repos="$(printf '%s' "$addons_repos_raw" | tr -d '[:space:]')"
openupgrade_repo="OCA/OpenUpgrade@${ODOO_VERSION:-19.0}"
case ",${addons_repos}," in
*,OCA/OpenUpgrade@*,* | *,OCA/OpenUpgrade,*) ;;
"",,)
	addons_repos="${openupgrade_repo}"
	;;
*)
	addons_repos="${addons_repos},${openupgrade_repo}"
	;;
esac

download_archive() {
	repository_full_name="$1"
	repository_ref="$2"
	target_directory="$3"

	archive_url="https://codeload.github.com/${repository_full_name}/tar.gz/${repository_ref}"
	tmp_archive="$(mktemp /tmp/addon-archive.XXXXXX)"
	tmp_extract_root="$(mktemp -d /tmp/addon-extract.XXXXXX)"

	log "Downloading ${repository_full_name}@${repository_ref}"
	if ! curl --fail --location --show-error --silent \
		-H "Authorization: Bearer ${GITHUB_TOKEN}" \
		-H "Accept: application/vnd.github+json" \
		"${archive_url}" \
		-o "${tmp_archive}"; then
		echo "Failed to download addon archive for ${repository_full_name}@${repository_ref}." >&2
		rm -f "${tmp_archive}"
		rm -rf "${tmp_extract_root}"
		exit 1
	fi

	if ! tar -xzf "${tmp_archive}" -C "${tmp_extract_root}"; then
		echo "Failed to extract addon archive for ${repository_full_name}@${repository_ref}." >&2
		rm -f "${tmp_archive}"
		rm -rf "${tmp_extract_root}"
		exit 1
	fi

	extracted_root="$(find "${tmp_extract_root}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
	if [ -z "${extracted_root}" ]; then
		echo "Missing extracted repository directory for ${repository_full_name}@${repository_ref}." >&2
		rm -f "${tmp_archive}"
		rm -rf "${tmp_extract_root}"
		exit 1
	fi

	rm -rf "${target_directory}"
	mkdir -p "$(dirname "${target_directory}")"
	mv "${extracted_root}" "${target_directory}"

	rm -f "${tmp_archive}"
	rm -rf "${tmp_extract_root}"
}

link_modules() {
	repo_root="$1"
	root_dir="$2"
	if [ -f "${repo_root}/__manifest__.py" ] || [ -f "${repo_root}/__openerp__.py" ]; then
		return
	fi
	scan_roots=""
	if [ -d "${repo_root}/enterprise" ]; then
		scan_roots="${scan_roots} ${repo_root}/enterprise"
	fi
	if [ -d "${repo_root}/addons" ]; then
		scan_roots="${scan_roots} ${repo_root}/addons"
	fi
	if [ -d "${repo_root}/odoo/addons" ]; then
		scan_roots="${scan_roots} ${repo_root}/odoo/addons"
	fi
	if [ -z "$scan_roots" ]; then
		scan_roots="${repo_root}"
	fi
	for scan_root in ${scan_roots}; do
		for module_dir in "${scan_root}"/*; do
			[ -d "$module_dir" ] || continue
			if [ ! -f "${module_dir}/__manifest__.py" ] && [ ! -f "${module_dir}/__openerp__.py" ]; then
				continue
			fi
			module_name="$(basename "$module_dir")"
			link_path="${root_dir}/${module_name}"
			if [ -e "$link_path" ]; then
				if [ "$(readlink "$link_path" 2>/dev/null)" != "$module_dir" ]; then
					echo "Module ${module_name} already exists in ${root_dir}; skipping link." >&2
				fi
				continue
			fi
			relative_target="$module_dir"
			case "$module_dir" in
			"${root_dir}"/*)
				relative_target="${module_dir#"$root_dir"/}"
				;;
			esac
			ln -s "$relative_target" "$link_path"
		done
	done
}

if [ -n "$addons_repos" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot download addons." >&2
		exit 1
	fi
	log "Downloading addon repositories: ${addons_repos}"
	old_ifs="$IFS"
	IFS=','
	for raw in ${addons_repos}; do
		repo="$(echo "$raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
		if [ -z "$repo" ]; then
			continue
		fi
		ref_name="main"
		case "$repo" in
		*@*)
			ref_name="${repo##*@}"
			repo="${repo%@*}"
			;;
		esac
		name="${repo##*/}"
		target_root="/extra_addons"
		download_archive "$repo" "$ref_name" "${target_root}/${name}"
		link_modules "${target_root}/${name}" "$target_root"
	done
	IFS="$old_ifs"
else
	log "ODOO_ADDON_REPOSITORIES is empty; skipping clone."
fi
